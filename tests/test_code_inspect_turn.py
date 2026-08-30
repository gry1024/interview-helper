"""Wire code_inspect into a turn: trigger, jail, clone_ok, no coordinates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app import repository
from app.agent import run_turn
from app.llm import complete_json_with_tools
from app.tools.code_inspect import CODE_COORDINATE, CODE_INSPECT_TOOL


DIRECTIONS = [
    {"id": "d1", "title": "输入表示", "goal": "问清 token 如何进入注意力"},
    {"id": "d2", "title": "训练流程", "goal": "问清预训练到对齐的衔接"},
    {"id": "d3", "title": "数据质量", "goal": "问清清洗规则与验证方法"},
]


def _write_minimind_fixture(root: Path) -> None:
    (root / "model.py").write_text(
        "def apply_rope(q, k):\n    return q, k\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("MiniMind decoder-only\n", encoding="utf-8")


def _session(session_id: str, *, clone_ok: bool) -> dict[str, Any]:
    return {
        "id": session_id,
        "role": "llm-algo",
        "statement": "复现了 RoPE、RMSNorm 与 SwiGLU。",
        "directions": DIRECTIONS,
        "current_direction_id": "d1",
        "clone_ok": clone_ok,
    }


def _legal_turn_json() -> dict[str, Any]:
    return {
        "thought": (
            "评价：声称了仓库里对不上的检索与训练规模。\n"
            "查代码：是，仓库未体现 rerank 与万卡。\n"
            "本方向结束：否，因为输入表示还没问清。"
        ),
        "direction_done": False,
        "next_question": "一个 token 变成向量之后，位置信息是怎样加进去的？",
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


def test_complete_json_with_tools_runs_then_parses_json(monkeypatch) -> None:
    completions = _FakeCompletions(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "c1",
                            "code_inspect",
                            json.dumps({"query": "rerank 万卡"}, ensure_ascii=False),
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json()))),
        ]
    )
    _install_client(monkeypatch, completions)
    seen: list[tuple[str, dict[str, Any]]] = []

    def run_tool(name: str, args: dict[str, Any]) -> str:
        seen.append((name, args))
        return "ok=true\nconclusion=仓库中未体现：rerank、万卡。"

    parsed = complete_json_with_tools(
        "system",
        "user",
        tools=[CODE_INSPECT_TOOL],
        run_tool=run_tool,
    )
    assert parsed["next_question"].startswith("一个 token")
    assert seen == [("code_inspect", {"query": "rerank 万卡"})]
    assert completions.calls[0]["tools"] == [CODE_INSPECT_TOOL]
    second_messages = completions.calls[1]["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert "未体现" in second_messages[-1]["content"]
    assert "tools" not in completions.calls[1]


def test_run_turn_triggers_inspect_without_leaking_coordinates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repos = tmp_path / "repos"
    monkeypatch.setattr(repository, "REPOS_DIR", repos)
    session_id = "session-tool-rerank"
    root = repos / session_id
    root.mkdir(parents=True)
    _write_minimind_fixture(root)

    completions = _FakeCompletions(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "c1",
                            "code_inspect",
                            json.dumps({"query": "rerank 万卡"}, ensure_ascii=False),
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json()))),
        ]
    )
    _install_client(monkeypatch, completions)

    result, next_id, tools = run_turn(
        session=_session(session_id, clone_ok=True),
        turns=[
            {
                "role": "interviewer",
                "body": "一个 token ID 进入模型后，先怎样变成 hidden state？",
            }
        ],
        answer="我还做了 rerank，并且在分布式万卡上训练过。",
    )
    assert next_id == "d1"
    assert result.direction_done is False
    assert "查代码：是" in result.thought
    assert "未体现" in result.thought
    assert CODE_COORDINATE.search(result.next_question) is None
    assert ".py:" not in result.next_question
    inspect_event = next(item for item in tools["events"] if item["name"] == "code_inspect")
    assert inspect_event["name"] == "code_inspect"
    assert ".py:" not in inspect_event["result"]
    assert "未体现" in inspect_event["result"]
    assert "internal_excerpt" in next(
        item["result"] for item in tools["meta"] if item["name"] == "code_inspect"
    )
    second_messages = completions.calls[1]["messages"]
    assert any(
        msg.get("role") == "tool" and "internal_excerpt" in msg.get("content", "")
        for msg in second_messages
    )


def test_run_turn_jail_path_hint_does_not_stop_interview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repos = tmp_path / "repos"
    monkeypatch.setattr(repository, "REPOS_DIR", repos)
    session_id = "session-tool-jail"
    root = repos / session_id
    root.mkdir(parents=True)
    _write_minimind_fixture(root)

    completions = _FakeCompletions(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "c1",
                            "code_inspect",
                            json.dumps(
                                {"query": "RoPE", "path_hint": "../etc/passwd"},
                                ensure_ascii=False,
                            ),
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json()))),
        ]
    )
    _install_client(monkeypatch, completions)

    result, next_id, tools = run_turn(
        session=_session(session_id, clone_ok=True),
        turns=[{"role": "interviewer", "body": "token 先怎么变成向量？"}],
        answer="我看了 /etc/passwd 和 model.py:12。",
    )
    assert next_id == "d1"
    assert result.next_question
    assert ".py:" not in result.next_question
    public = next(item["result"] for item in tools["events"] if item["name"] == "code_inspect")
    assert "root:x:" not in public
    assert "/etc/passwd" not in public
    assert CODE_COORDINATE.search(result.next_question) is None


def test_run_turn_clone_ok_false_keeps_interview_going(monkeypatch) -> None:
    completions = _FakeCompletions(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "c1",
                            "code_inspect",
                            json.dumps({"query": "rerank"}, ensure_ascii=False),
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json()))),
        ]
    )
    _install_client(monkeypatch, completions)

    result, next_id, tools = run_turn(
        session=_session("session-no-clone", clone_ok=False),
        turns=[{"role": "interviewer", "body": "token 先怎么变成向量？"}],
        answer="我做了 rerank 和万卡训练。",
    )
    assert next_id == "d1"
    assert result.direction_done is False
    assert "不可用" in next(
        item["result"] for item in tools["events"] if item["name"] == "code_inspect"
    )
    assert ".py:" not in result.next_question


def test_run_turn_forces_inspect_when_model_skips_fabricated_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repos = tmp_path / "repos"
    monkeypatch.setattr(repository, "REPOS_DIR", repos)
    session_id = "session-force-rerank"
    root = repos / session_id
    root.mkdir(parents=True)
    _write_minimind_fixture(root)

    completions = _FakeCompletions(
        [_FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json())))]
    )
    _install_client(monkeypatch, completions)

    result, next_id, tools = run_turn(
        session=_session(session_id, clone_ok=True),
        turns=[{"role": "interviewer", "body": "token 先怎么变成向量？", "direction_id": "d1"}],
        answer="这块我大概会。另外我还做了 rerank，并且在分布式万卡上训练过。",
    )
    assert next_id == "d1"
    assert result.direction_done is False
    assert tools["events"]
    inspect_event = next(item for item in tools["events"] if item["name"] == "code_inspect")
    assert "查代码：是" in result.thought
    assert "未体现" in inspect_event["result"]
    assert "rerank" in inspect_event["result"]
    assert "万卡" in inspect_event["result"]
    assert CODE_COORDINATE.search(result.next_question) is None


def test_run_turn_retries_when_question_has_coordinates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repos = tmp_path / "repos"
    monkeypatch.setattr(repository, "REPOS_DIR", repos)
    session_id = "session-tool-retry"
    root = repos / session_id
    root.mkdir(parents=True)
    _write_minimind_fixture(root)

    bad = dict(_legal_turn_json())
    bad["next_question"] = "请看 model.py:12 的 RoPE？"
    completions = _FakeCompletions(
        [
            _FakeResponse(_FakeMessage(content=json.dumps(bad))),
            _FakeResponse(_FakeMessage(content=json.dumps(_legal_turn_json()))),
        ]
    )
    _install_client(monkeypatch, completions)

    result, next_id, _tools = run_turn(
        session=_session(session_id, clone_ok=True),
        turns=[{"role": "interviewer", "body": "token 先怎么变成向量？"}],
        answer="用了 RoPE。",
    )
    assert next_id == "d1"
    assert ".py:" not in result.next_question
    assert "model.py" not in result.next_question
    assert result.next_question
    assert len(completions.calls) == 1
