"""Wire code_exercise into turns SSE and code-submissions."""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import db
from app import main as main_mod
from app.agent import requested_code_exercise_args, run_turn
from app.llm import complete_json_with_tools
from app.models import TurnResult
from app.tools.code_exercise import CODE_EXERCISE_TOOL
from app.tools.code_inspect import CODE_INSPECT_TOOL


DIRECTIONS = [
    {"id": "d1", "title": "输入表示", "goal": "问清 token 如何进入注意力"},
    {"id": "d2", "title": "训练流程", "goal": "问清预训练到对齐的衔接"},
    {"id": "d3", "title": "数据质量", "goal": "问清清洗规则与验证方法"},
]


def _session(session_id: str = "session-code-ex") -> dict[str, Any]:
    return {
        "id": session_id,
        "role": "llm-algo",
        "statement": "复现了 RoPE、RMSNorm 与 SwiGLU。",
        "directions": DIRECTIONS,
        "current_direction_id": "d1",
        "clone_ok": False,
    }


def _legal_turn_json() -> dict[str, Any]:
    return {
        "thought": (
            "评价：机制说到注意力，适合核实会不会写。\n"
            "查代码：否\n"
            "本方向结束：否，因为输入表示还没问清。"
        ),
        "direction_done": False,
        "next_question": "编辑器里先写出 Q 的投影公式？",
    }


class _FakeFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[_FakeToolCall] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message: _FakeMessage) -> None:
        self.message = message


class _FakeResponse:
    def __init__(self, message: _FakeMessage) -> None:
        self.choices = [_FakeChoice(message)]


class _FakeCompletions:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("unexpected extra completion call")
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = type("Chat", (), {"completions": completions})()


def _install_client(monkeypatch, completions: _FakeCompletions) -> None:
    monkeypatch.setattr("app.llm._client", lambda: _FakeClient(completions))


def _seed_session(session_id: str) -> None:
    db.create_session(
        session_id=session_id,
        github_url="https://github.com/jingyaogong/minimind.git",
        statement="复现了 RoPE、RMSNorm 与 SwiGLU。",
        role="llm-algo",
        directions=DIRECTIONS,
        clone_path=None,
        clone_ok=False,
        first_question="一个 token ID 进入模型后，先怎样变成 hidden state？",
    )


def test_complete_json_with_tools_keeps_inspect_and_exercise(monkeypatch) -> None:
    completions = _FakeCompletions(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "c1",
                            "code_exercise",
                            json.dumps({"exercise_id": "mha-forward"}),
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json()))),
        ]
    )
    _install_client(monkeypatch, completions)
    seen: list[str] = []

    def run_tool(name: str, args: dict[str, Any]) -> str:
        seen.append(name)
        return "ok=true"

    parsed = complete_json_with_tools(
        "system",
        "user",
        tools=[CODE_INSPECT_TOOL, CODE_EXERCISE_TOOL],
        run_tool=run_tool,
    )
    assert parsed["direction_done"] is False
    assert seen == ["code_exercise"]
    assert completions.calls[0]["tools"] == [CODE_INSPECT_TOOL, CODE_EXERCISE_TOOL]


def test_run_turn_opens_catalog_exercise_not_invented(monkeypatch) -> None:
    completions = _FakeCompletions(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "c1",
                            "code_exercise",
                            json.dumps({"exercise_id": "mha-forward"}),
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json()))),
        ]
    )
    _install_client(monkeypatch, completions)

    result, next_id, tools = run_turn(
        session=_session(),
        turns=[{"role": "interviewer", "body": "注意力下一步怎么算？", "direction_id": "d1"}],
        answer="我说到 Multi-Head Attention 了，可以手写前向。",
    )
    assert next_id == "d1"
    assert result.direction_done is False
    assert tools["events"]
    event = tools["events"][0]
    assert event["name"] == "code_exercise"
    assert event["payload"]["exercise_id"] == "mha-forward"
    assert event["payload"]["language"] == "python"
    assert "Multi-Head" in event["payload"]["title"]
    assert event["payload"]["starter"]
    assert "已打开手撕题" in event["result"]
    assert CODE_INSPECT_TOOL in completions.calls[0]["tools"]
    assert CODE_EXERCISE_TOOL in completions.calls[0]["tools"]
    from app.tools.search_library import SEARCH_LIBRARY_TOOL

    assert SEARCH_LIBRARY_TOOL in completions.calls[0]["tools"]


def test_run_turn_rejects_invented_exercise_id(monkeypatch) -> None:
    completions = _FakeCompletions(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "c1",
                            "code_exercise",
                            json.dumps({"exercise_id": "two-sum-leetcode"}),
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json()))),
        ]
    )
    _install_client(monkeypatch, completions)

    _result, _next_id, tools = run_turn(
        session=_session(),
        turns=[{"role": "interviewer", "body": "下一问", "direction_id": "d1"}],
        answer="我可以写两数之和。",
    )
    event = tools["events"][0]
    assert event["name"] == "code_exercise"
    assert event.get("payload") is None
    assert "无法打开" in event["result"]


def test_run_turn_forces_exercise_when_student_asks_to_write(monkeypatch) -> None:
    completions = _FakeCompletions(
        [_FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json())))]
    )
    _install_client(monkeypatch, completions)

    result, next_id, tools = run_turn(
        session=_session(),
        turns=[{"role": "interviewer", "body": "RoPE 加在哪？", "direction_id": "d1"}],
        answer="RoPE 旋 Q/K。请打开手撕题，让我手写 apply_rope。",
    )
    assert next_id == "d1"
    assert result.direction_done is False
    assert requested_code_exercise_args(answer="请打开手撕题") is not None
    event = next(item for item in tools["events"] if item["name"] == "code_exercise")
    assert event["payload"]["exercise_id"] == "rope-apply"
    assert "已打开手撕题" in event["result"]


def test_run_turn_submission_does_not_offer_exercise_tool(monkeypatch) -> None:
    completions = _FakeCompletions(
        [_FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json())))]
    )
    _install_client(monkeypatch, completions)
    run_turn(
        session=_session(),
        turns=[{"role": "interviewer", "body": "写 MHA", "direction_id": "d1"}],
        answer="[手撕提交 exercise_id=mha-forward]\n学生代码：\npass",
        allow_code_exercise=False,
    )
    from app.tools.search_library import SEARCH_LIBRARY_TOOL

    assert completions.calls[0]["tools"] == [CODE_INSPECT_TOOL, SEARCH_LIBRARY_TOOL]


def test_turns_sse_emits_code_exercise_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session("session-sse-ex")
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    fake = TurnResult.model_validate(_legal_turn_json())
    payload = {
        "exercise_id": "mha-forward",
        "title": "手撕 Multi-Head Attention",
        "prompt": "用 Python 实现 Multi-Head Attention",
        "language": "python",
        "starter": "class MultiHeadAttention:\n    pass\n",
    }
    monkeypatch.setattr(
        "app.main.run_turn",
        lambda **_kwargs: (
            fake,
            "d1",
            {
                "events": [
                    {
                        "name": "code_exercise",
                        "args": {"exercise_id": "mha-forward"},
                        "result": "已打开手撕题：手撕 Multi-Head Attention",
                        "payload": payload,
                    }
                ],
                "meta": [
                    {
                        "name": "code_exercise",
                        "args": {"exercise_id": "mha-forward"},
                        "result": "ok=true",
                        "exercise_id": "mha-forward",
                    }
                ],
            },
        ),
    )

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/api/sessions/session-sse-ex/turns",
            json={"answer": "我说到 Multi-Head Attention 了。"},
        )

    assert response.status_code == 200
    body = response.text
    assert "event: code_exercise" in body
    assert "event: tool" in body
    assert "mha-forward" in body
    assert "event: thought_delta" in body
    assert "event: question" in body
    assert "event: done" in body
    assert db.get_session("session-sse-ex")["status"] == "live"


def test_turns_still_work_after_editor_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session("session-editor-open")
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    fake = TurnResult.model_validate(_legal_turn_json())
    monkeypatch.setattr(
        "app.main.run_turn",
        lambda **_kwargs: (fake, "d1", {"events": [], "meta": []}),
    )

    with TestClient(main_mod.app) as client:
        first = client.post(
            "/api/sessions/session-editor-open/turns",
            json={"answer": "这题用什么 API？"},
        )
        second = client.post(
            "/api/sessions/session-editor-open/turns",
            json={"answer": "shape 是 (batch, seq, d_model)。"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "event: question" in second.text
    assert db.get_session("session-editor-open")["status"] == "live"


def test_code_submission_runs_turn_and_keeps_session_live(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session("session-submit")
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    fake = TurnResult.model_validate(_legal_turn_json())
    seen: list[dict[str, Any]] = []

    def _fake_run_turn(**kwargs: Any) -> tuple[TurnResult, str, dict[str, Any]]:
        seen.append(kwargs)
        return fake, "d1", {"events": [], "meta": []}

    monkeypatch.setattr("app.main.run_turn", _fake_run_turn)
    code = "class MultiHeadAttention:\n    def forward(self, x, mask=None):\n        return x\n"

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/api/sessions/session-submit/code-submissions",
            json={"exercise_id": "mha-forward", "code": code},
        )
        follow = client.post(
            "/api/sessions/session-submit/turns",
            json={"answer": "提交之后我还想问缩放为什么除 d_k。"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: thought_delta" in response.text
    assert "event: question" in response.text
    assert "event: done" in response.text
    assert follow.status_code == 200
    assert seen[0]["allow_code_exercise"] is False
    assert "mha-forward" in seen[0]["answer"]
    assert code.strip() in seen[0]["answer"]

    user = next(item for item in db.list_turns("session-submit") if item["role"] == "user")
    assert user["body"] == code.strip()
    assert user["meta"] == {"kind": "code_submission", "exercise_id": "mha-forward"}
    assert db.get_session("session-submit")["status"] == "live"


def test_code_submission_rejects_unknown_and_ended(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session("session-bad-ex")
    _seed_session("session-ended-ex")
    with closing(db.connect()) as connection:
        connection.execute(
            "UPDATE sessions SET status = 'ended' WHERE id = ?",
            ("session-ended-ex",),
        )
        connection.commit()
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    with TestClient(main_mod.app) as client:
        unknown = client.post(
            "/api/sessions/session-bad-ex/code-submissions",
            json={"exercise_id": "two-sum-leetcode", "code": "print(1)"},
        )
        ended = client.post(
            "/api/sessions/session-ended-ex/code-submissions",
            json={"exercise_id": "mha-forward", "code": "print(1)"},
        )
        missing = client.post(
            "/api/sessions/no-such-session/code-submissions",
            json={"exercise_id": "mha-forward", "code": "print(1)"},
        )

    assert unknown.status_code == 400
    assert ended.status_code == 409
    assert missing.status_code == 404
