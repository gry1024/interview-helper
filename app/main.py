"""FastAPI entry point for the Interview Helper web application."""

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import json
import logging
import math
from pathlib import Path
import re
from time import monotonic
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.agent import plan_directions, run_turn, write_report
from app.db import (
    append_help,
    append_turn_bundle,
    create_session,
    get_session,
    init_db,
    list_helps,
    list_turns,
    save_review_and_end_session,
)
from app.db_reviews import get_review, list_reviews
from app.llm import LLMError
from app.models import (
    CodeSubmissionCreate,
    DirectionPlan,
    SessionCreate,
    SessionCreated,
    TeacherHintCreate,
    TurnCreate,
)
from app.teacher import write_teacher_hint
from app.tools.code_exercise import format_submission_answer, get_exercise
from app.report import dump_end_snapshot
from app.repository import (
    CloneResult,
    cleanup_session_repo,
    clone_repository,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
JD_DIR = ROOT_DIR / "app" / "jd"
logger = logging.getLogger(__name__)
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


_GRAD_EDU_FIELD = re.compile(r"硕士|博士|master'?s?\b|ph\.?\s*d\.?", re.I)
_BACHELOR_FIELD = re.compile(r"本科|学士|bachelor", re.I)
_GRAD_REQUIRE_TEXT = re.compile(
    r"硕士及以上|博士及以上|硕士研究生及以上|"
    r"(?:学历|要求)[^\n。]{0,20}(?:硕士|博士)|"
    r"(?:仅限|必须|须为)[^\n。]{0,8}(?:硕士|博士)|"
    r"(?:硕士|博士)[^\n。]{0,8}(?:学历|及以上|起步)|"
    r"master'?s(?:\s+degree)?\s+(?:or\s+above|and\s+above|required)|"
    r"ph\.?\s*d\.?\s+(?:or\s+above|required)",
    re.I,
)


def _load_samples(filename: str) -> list[dict[str, Any]]:
    with (JD_DIR / filename).open(encoding="utf-8") as source_file:
        samples = json.load(source_file)

    return [
        sample
        for sample in samples
        if sample.get("source_url") and sample.get("source_name")
    ]


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_field_text(item) for item in value)
    return str(value)


def _sample_kind(sample: dict[str, Any], fallback: str) -> str:
    kind = str(sample.get("kind") or "").strip().lower()
    if kind in {"interview", "面经"}:
        return "interview"
    if kind in {"jd", "job"}:
        return "jd"
    return fallback


def is_graduate_targeted(sample: dict[str, Any]) -> bool:
    """True when a sample is aimed at 硕士/博士, not 本科生."""

    education = _field_text(sample.get("education")).strip()
    if education and _GRAD_EDU_FIELD.search(education):
        if _BACHELOR_FIELD.search(education) and not re.search(
            r"硕士及以上|仅限硕士|仅限博士|博士",
            education,
        ):
            return False
        return True

    blob = "\n".join(
        [
            education,
            _field_text(sample.get("requirements")),
            _field_text(sample.get("text")),
            _field_text(sample.get("experience")),
        ]
    )
    return bool(_GRAD_REQUIRE_TEXT.search(blob))


def is_xiaohongshu_sample(sample: dict[str, Any]) -> bool:
    blob = f"{sample.get('source_name', '')} {sample.get('source_url', '')}".lower()
    return "小红书" in blob or "xiaohongshu" in blob or "xhslink" in blob


def _library_sort_key(sample: dict[str, Any]) -> tuple[int, str, str]:
    return (
        0 if is_xiaohongshu_sample(sample) else 1,
        str(sample.get("captured_at") or sample.get("published_at") or ""),
        str(sample.get("id") or sample.get("source_url") or ""),
    )


def publish_library() -> dict[str, list[dict[str, Any]]]:
    """Split by kind and hide graduate-only posts for the undergrad audience."""

    buckets: dict[str, list[dict[str, Any]]] = {"jds": [], "interviews": []}
    for filename, fallback in (("jds.json", "jd"), ("interviews.json", "interview")):
        for sample in _load_samples(filename):
            if is_graduate_targeted(sample):
                continue
            if _sample_kind(sample, fallback) == "interview":
                buckets["interviews"].append(sample)
            else:
                buckets["jds"].append(sample)
    buckets["jds"].sort(key=_library_sort_key)
    buckets["interviews"].sort(key=_library_sort_key)
    return buckets


@app.get("/api/jds")
def list_job_samples() -> dict[str, list[dict[str, Any]]]:
    """Return sourced JD/interview samples filtered for undergraduates."""

    return publish_library()


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


def _sse_tool(name: str, args: dict[str, Any], result: str) -> str:
    """Emit a candidate-safe tool event; excerpts stay in meta_json."""

    return _sse("tool", {"name": name, "args": args, "result": result})


def _sse_tool_events(tool_events: list[dict[str, Any]]) -> list[str]:
    chunks: list[str] = []
    for event in tool_events:
        payload = event.get("payload")
        if event.get("name") == "code_exercise" and isinstance(payload, dict):
            chunks.append(_sse("code_exercise", payload))
        chunks.append(
            _sse_tool(
                event.get("name") or "code_inspect",
                event.get("args") or {},
                event.get("result") or "",
            )
        )
    return chunks


def _require_live_session(session: dict[str, Any] | None, session_id: str) -> dict[str, Any]:
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
    return session


def _chunk_thought(thought: str) -> list[str]:
    pieces = [piece for piece in _THOUGHT_SPLIT.split(thought) if piece]
    return pieces or [thought]


def _turn_sse_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def _stream_run_turn(
    *,
    session_id: str,
    session: dict[str, Any],
    answer: str,
    stored_answer: str | None = None,
    user_meta: dict[str, Any] | None = None,
    allow_code_exercise: bool = True,
) -> StreamingResponse:
    _active_turns.add(session_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            turns = await asyncio.to_thread(list_turns, session_id)
            try:
                result, next_direction_id, tool_bundle = await asyncio.to_thread(
                    run_turn,
                    session=session,
                    turns=turns,
                    answer=answer,
                    allow_code_exercise=allow_code_exercise,
                )
            except LLMError:
                yield _sse("error", {"message": "MiniMax 暂时无法继续追问，请稍后重试"})
                yield _sse("done", {})
                return
            except Exception:
                logger.exception("turn stream failed")
                yield _sse("error", {"message": "本轮追问失败，请稍后重试"})
                yield _sse("done", {})
                return

            tool_events = tool_bundle.get("events") or []
            tool_meta = tool_bundle.get("meta") or []
            for chunk in _sse_tool_events(tool_events):
                yield chunk

            for chunk in _chunk_thought(result.thought):
                yield _sse("thought_delta", {"text": chunk})
                await asyncio.sleep(0.02)

            await asyncio.to_thread(
                append_turn_bundle,
                session_id=session_id,
                user_answer=stored_answer if stored_answer is not None else answer,
                thought=result.thought,
                next_question=result.next_question,
                direction_id=session["current_direction_id"],
                next_direction_id=next_direction_id,
                meta=tool_meta or None,
                user_meta=user_meta,
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
        headers=_turn_sse_headers(),
    )


@app.post("/api/sessions/{session_id}/turns")
async def create_turn(
    session_id: str,
    payload: TurnCreate,
    request: Request,
) -> StreamingResponse:
    """Stream one locked-topic interview turn as SSE."""

    _enforce_write_rate_limit(request)
    session = _require_live_session(
        await asyncio.to_thread(get_session, session_id),
        session_id,
    )
    return _stream_run_turn(
        session_id=session_id,
        session=session,
        answer=payload.answer,
    )


@app.post("/api/sessions/{session_id}/code-submissions")
async def submit_code(
    session_id: str,
    payload: CodeSubmissionCreate,
    request: Request,
) -> StreamingResponse:
    """Store a hand-written solution and continue the interview as a normal turn."""

    _enforce_write_rate_limit(request)
    exercise = get_exercise(payload.exercise_id)
    if exercise is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="题库无此题")
    session = _require_live_session(
        await asyncio.to_thread(get_session, session_id),
        session_id,
    )
    return _stream_run_turn(
        session_id=session_id,
        session=session,
        answer=format_submission_answer(exercise, payload.code),
        stored_answer=payload.code,
        user_meta={"kind": "code_submission", "exercise_id": exercise.id},
        allow_code_exercise=False,
    )


@app.post("/api/sessions/{session_id}/hints")
async def create_hint(
    session_id: str,
    payload: TeacherHintCreate,
    request: Request,
) -> dict[str, Any]:
    """Ask the teacher for a side hint. Does not consume the interview turn."""

    _enforce_write_rate_limit(request)
    session = _require_live_session(
        await asyncio.to_thread(get_session, session_id),
        session_id,
    )
    turns = await asyncio.to_thread(list_turns, session_id)
    try:
        result, bundle = await asyncio.to_thread(
            write_teacher_hint,
            session=session,
            turns=turns,
            question=payload.question,
        )
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="老师暂时无法给出提示，请稍后重试",
        ) from exc

    inspect_public = None
    for event in bundle.get("events") or []:
        if event.get("name") == "code_inspect":
            inspect_public = event.get("result")
    record = await asyncio.to_thread(
        append_help,
        session_id=session_id,
        question=(payload.question or "").strip()
        or next(
            (
                turn["body"]
                for turn in reversed(turns)
                if turn.get("role") == "interviewer"
            ),
            "",
        ),
        hint=result.hint,
        looked_at_code=result.looked_at_code,
        inspect_public=inspect_public,
        direction_id=session.get("current_direction_id"),
    )
    return {
        "id": record["id"],
        "hint": result.hint,
        "looked_at_code": result.looked_at_code,
        "question": record["question"],
    }


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: str, request: Request) -> StreamingResponse:
    """Generate the end report, freeze the snapshot, and mark the session ended."""

    _enforce_write_rate_limit(request)
    session = await asyncio.to_thread(get_session, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if session["status"] not in {"ready", "live"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="会话已结束，无法再次生成报告",
        )
    if session_id in _active_turns:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="本场已有一轮回答正在处理",
        )

    _active_turns.add(session_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            yield ": preparing-report\n\n"
            turns = await asyncio.to_thread(list_turns, session_id)
            helps = await asyncio.to_thread(list_helps, session_id)
            try:
                report_text, tool_bundle = await asyncio.to_thread(
                    write_report,
                    session,
                    turns,
                    helps,
                )
                snapshot_json = dump_end_snapshot(session, turns, report_text, helps)
                await asyncio.to_thread(
                    save_review_and_end_session,
                    session_id=session_id,
                    report_text=report_text,
                    snapshot_json=snapshot_json,
                )
            except LLMError:
                yield _sse("error", {"message": "MiniMax 暂时无法生成报告，请稍后重试"})
                yield _sse("done", {})
                return
            except Exception:
                logger.exception("end report stream failed")
                yield _sse("error", {"message": "结束报告生成失败，请稍后重试"})
                yield _sse("done", {})
                return

            for event in tool_bundle.get("events") or []:
                yield _sse_tool(
                    event.get("name") or "code_inspect",
                    event.get("args") or {},
                    event.get("result") or "",
                )

            for chunk in _chunk_thought(report_text):
                yield _sse("report_delta", {"text": chunk})
                await asyncio.sleep(0.02)

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


@app.get("/api/reviews")
async def read_reviews() -> list[dict[str, str]]:
    """List frozen reviews. Preview is derived at read time; nothing is rewritten."""

    return await asyncio.to_thread(list_reviews)


@app.get("/api/reviews/{review_id}")
async def read_review(review_id: str) -> Response:
    """Return the stored snapshot_json string as-is. Do not re-serialize."""

    row = await asyncio.to_thread(get_review, review_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复盘不存在")
    return Response(
        content=row["snapshot_json"],
        media_type="application/json; charset=utf-8",
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
