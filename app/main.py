"""FastAPI entry point for the Interview Helper web application."""

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
from time import monotonic
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.agent import plan_directions, run_turn
from app.db import (
    append_turn_bundle,
    create_session,
    get_session,
    init_db,
    list_turns,
)
from app.llm import LLMError
from app.models import DirectionPlan, SessionCreate, SessionCreated, TurnCreate
from app.repository import (
    CloneResult,
    cleanup_session_repo,
    clone_repository,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
JD_DIR = ROOT_DIR / "app" / "jd"
RATE_LIMIT = 10
RATE_WINDOW_SECONDS = 60
_write_requests: defaultdict[str, deque[float]] = defaultdict(deque)
_active_turns: set[str] = set()
_THOUGHT_SPLIT = re.compile(r"(?<=[。！？\n])")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Interview Helper", lifespan=lifespan)


@app.middleware("http")
async def disable_static_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in {"/", "/index.html", "/app.js", "/styles.css"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a small readiness response for local and public checks."""

    return {"status": "ok"}


def _load_samples(filename: str) -> list[dict[str, Any]]:
    with (JD_DIR / filename).open(encoding="utf-8") as source_file:
        samples = json.load(source_file)

    return [
        sample
        for sample in samples
        if sample.get("source_url") and sample.get("source_name")
    ]


@app.get("/api/jds")
def list_job_samples() -> dict[str, list[dict[str, Any]]]:
    """Return only sourced JD and interview samples."""

    return {
        "jds": _load_samples("jds.json"),
        "interviews": _load_samples("interviews.json"),
    }


def _enforce_write_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = monotonic()
    timestamps = _write_requests[client_ip]
    while timestamps and now - timestamps[0] >= RATE_WINDOW_SECONDS:
        timestamps.popleft()
    if len(timestamps) >= RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
        )
    timestamps.append(now)


@app.post(
    "/api/sessions",
    response_model=SessionCreated,
    status_code=status.HTTP_201_CREATED,
)
async def start_session(payload: SessionCreate, request: Request) -> SessionCreated:
    """Create a fixed interview plan while preparing its repository in parallel."""

    _enforce_write_rate_limit(request)
    session_id = str(uuid4())
    clone_result, plan_result = await asyncio.gather(
        asyncio.to_thread(clone_repository, payload.github_url, session_id),
        asyncio.to_thread(plan_directions, payload.statement, payload.role),
        return_exceptions=True,
    )

    if isinstance(plan_result, BaseException):
        await asyncio.to_thread(cleanup_session_repo, session_id)
        message = (
            "MiniMax 暂时无法生成面试方向，请稍后重试"
            if isinstance(plan_result, LLMError)
            else "面试方向生成失败，请稍后重试"
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=message,
        ) from None

    if isinstance(clone_result, BaseException):
        clone_result = CloneResult(
            path=None,
            ok=False,
            error="仓库准备失败，代码核对暂不可用",
        )

    if not isinstance(plan_result, DirectionPlan):
        await asyncio.to_thread(cleanup_session_repo, session_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="面试方向格式无效，请稍后重试",
        )
    if not isinstance(clone_result, CloneResult):
        clone_result = CloneResult(
            path=None,
            ok=False,
            error="仓库准备失败，代码核对暂不可用",
        )

    directions = [direction.model_dump() for direction in plan_result.directions]
    try:
        await asyncio.to_thread(
            create_session,
            session_id=session_id,
            github_url=payload.github_url,
            statement=payload.statement,
            role=payload.role,
            directions=directions,
            clone_path=clone_result.path,
            clone_ok=clone_result.ok,
            first_question=plan_result.first_question,
        )
    except Exception as exc:
        await asyncio.to_thread(cleanup_session_repo, session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="会话保存失败，请稍后重试",
        ) from exc

    return SessionCreated(
        id=session_id,
        directions=plan_result.directions,
        first_question=plan_result.first_question,
        clone_ok=clone_result.ok,
        clone_error=clone_result.error,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunk_thought(thought: str) -> list[str]:
    pieces = [piece for piece in _THOUGHT_SPLIT.split(thought) if piece]
    return pieces or [thought]


@app.post("/api/sessions/{session_id}/turns")
async def create_turn(
    session_id: str,
    payload: TurnCreate,
    request: Request,
) -> StreamingResponse:
    """Stream one locked-topic interview turn as SSE."""

    _enforce_write_rate_limit(request)
    session = await asyncio.to_thread(get_session, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if session["status"] not in {"ready", "live"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="会话已结束，无法继续回答",
        )
    if session_id in _active_turns:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="本场已有一轮回答正在处理",
        )

    _active_turns.add(session_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            turns = await asyncio.to_thread(list_turns, session_id)
            try:
                result, next_direction_id = await asyncio.to_thread(
                    run_turn,
                    session=session,
                    turns=turns,
                    answer=payload.answer,
                )
            except LLMError:
                yield _sse("error", {"message": "MiniMax 暂时无法继续追问，请稍后重试"})
                yield _sse("done", {})
                return
            except Exception:
                yield _sse("error", {"message": "本轮追问失败，请稍后重试"})
                yield _sse("done", {})
                return

            for chunk in _chunk_thought(result.thought):
                yield _sse("thought_delta", {"text": chunk})
                await asyncio.sleep(0.02)

            await asyncio.to_thread(
                append_turn_bundle,
                session_id=session_id,
                user_answer=payload.answer,
                thought=result.thought,
                next_question=result.next_question,
                direction_id=session["current_direction_id"],
                next_direction_id=next_direction_id,
                meta=None,
            )

            yield _sse(
                "question",
                {
                    "text": result.next_question,
                    "direction_id": next_direction_id,
                    "direction_done": result.direction_done,
                },
            )
            yield _sse("done", {})
        finally:
            _active_turns.discard(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
