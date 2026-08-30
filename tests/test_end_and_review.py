"""End-report wiring: freeze snapshot, forbid later turns, replay as stored JSON."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import db
from app import main as main_mod
from app.agent import write_report
from app.db_reviews import ReviewAlreadyExistsError, get_review, save_review
from app.llm import LLMError
from app.report import (
    REPORT_SECTION_TITLES,
    _has_section_title,
    compose_report_text,
    dump_end_snapshot,
    extract_primary_band,
)
from tests.test_report_snapshot import (
    MIND_STATEMENT,
    _sample_report,
    _sample_session,
    _sample_turns,
)


DIRECTIONS = [
    {"id": "d1", "title": "架构组件", "goal": "从输入问到注意力输出"},
    {"id": "d2", "title": "训练流水线", "goal": "问清预训练到 DPO 的衔接"},
    {"id": "d3", "title": "数据与指令", "goal": "问清清洗与模板如何验证"},
]


def _seed_live_session(session_id: str = "session-end") -> None:
    db.create_session(
        session_id=session_id,
        github_url="https://github.com/jingyaogong/minimind.git",
        statement=MIND_STATEMENT,
        role="llm-algo",
        directions=DIRECTIONS,
        clone_path=None,
        clone_ok=False,
        first_question="一个 token ID 进入模型后，先怎样变成 hidden state？",
    )
    db.append_turn_bundle(
        session_id=session_id,
        user_answer="用了 RoPE 提升外推，另外我做了 rerank 和万卡分布式。",
        thought=(
            "评价：只报了组件名字。\n"
            "查代码：是，仓库未体现 rerank / 万卡。\n"
            "本方向结束：否，因为输入到注意力还没问完。"
        ),
        next_question="这个 token 的向量接下来怎么进注意力？",
        direction_id="d1",
        next_direction_id="d1",
        meta=[
            {
                "name": "code_inspect",
                "args": {"query": "rerank 万卡"},
                "result": "未把 rerank / 万卡分布式训练写成主线实现。",
            }
        ],
    )


def test_save_review_and_end_is_insert_only_same_transaction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_live_session("session-freeze")

    session = db.get_session("session-freeze")
    turns = db.list_turns("session-freeze")
    report_text = _sample_report()
    snapshot_json = dump_end_snapshot(session, turns, report_text)

    saved = db.save_review_and_end_session(
        session_id="session-freeze",
        report_text=report_text,
        snapshot_json=snapshot_json,
    )
    ended = db.get_session("session-freeze")
    stored = get_review("session-freeze")

    assert ended is not None
    assert ended["status"] == "ended"
    assert stored is not None
    assert stored["snapshot_json"] == snapshot_json
    assert stored["report_text"] == report_text
    assert stored["snapshot_json"] == saved["snapshot_json"]
    payload = json.loads(stored["snapshot_json"])
    assert payload["session"]["statement"] == MIND_STATEMENT
    assert payload["report"]["text"] == report_text
    for turn in turns:
        assert payload["turns"][turn["seq"]]["body"] == turn["body"]
    assert stored["report_text"] == report_text

    with pytest.raises(ReviewAlreadyExistsError):
        save_review(
            session_id="session-freeze",
            report_text=report_text,
            snapshot_json=snapshot_json,
        )


def test_end_endpoint_streams_report_then_forbids_turns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_live_session("session-end-sse")
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    report_text = _sample_report()
    public = "仓库未体现 rerank / 万卡，价值仍在训练闭环。"

    def fake_write_report(session, turns, helps=None):
        assert session["id"] == "session-end-sse"
        assert turns[1]["body"].startswith("用了 RoPE")
        return (
            report_text,
            {
                "events": [
                    {
                        "name": "code_inspect",
                        "args": {"query": "价值 改造"},
                        "result": public,
                    }
                ],
                "meta": [],
            },
        )

    monkeypatch.setattr("app.main.write_report", fake_write_report)

    with TestClient(main_mod.app) as client:
        response = client.post("/api/sessions/session-end-sse/end")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = response.text
        assert "event: tool" in body
        assert "event: report_delta" in body
        assert "event: done" in body
        assert "event: error" not in body
        assert "总评" in body
        assert "岗位匹配" in body
        assert public in body

        blocked = client.post(
            "/api/sessions/session-end-sse/turns",
            json={"answer": "继续答也不行"},
        )
        assert blocked.status_code == 409

        stored = db.get_session("session-end-sse")
        review = get_review("session-end-sse")
        assert stored is not None and stored["status"] == "ended"
        assert review is not None
        assert review["report_text"] == report_text
        expected = dump_end_snapshot(
            stored,
            db.list_turns("session-end-sse"),
            report_text,
        )
        assert review["snapshot_json"] == expected
        detail = client.get("/api/reviews/session-end-sse")
        assert detail.status_code == 200
        assert detail.text == review["snapshot_json"]
        replayed = json.loads(detail.text)
        assert replayed["session"]["statement"] == MIND_STATEMENT
        assert replayed["report"]["text"] == report_text
        live_turns = db.list_turns("session-end-sse")
        for turn in live_turns:
            assert replayed["turns"][turn["seq"]]["body"] == turn["body"]


def test_review_http_does_not_call_generators(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_live_session("session-replay")
    session = db.get_session("session-replay")
    turns = db.list_turns("session-replay")
    report_text = _sample_report()
    raw = dump_end_snapshot(session, turns, report_text)
    db.save_review_and_end_session(
        session_id="session-replay",
        report_text=report_text,
        snapshot_json=raw,
    )

    def forbid(name: str):
        def _raise(*_args, **_kwargs):
            raise AssertionError(f"复盘读取不得调用 {name} 改写")

        return _raise

    monkeypatch.setattr("app.agent.write_report", forbid("write_report"))
    monkeypatch.setattr("app.main.write_report", forbid("write_report"))
    monkeypatch.setattr("app.report.build_report_from_parts", forbid("build_report_from_parts"))
    monkeypatch.setattr("app.report.compose_report_text", forbid("compose_report_text"))
    monkeypatch.setattr(
        "app.report.assemble_review_snapshot", forbid("assemble_review_snapshot")
    )
    monkeypatch.setattr("app.report.dump_end_snapshot", forbid("dump_end_snapshot"))
    monkeypatch.setattr(
        "app.report.build_end_report_context", forbid("build_end_report_context")
    )

    main_mod._write_requests.clear()
    with TestClient(main_mod.app) as client:
        listing = client.get("/api/reviews")
        detail = client.get("/api/reviews/session-replay")

    assert listing.status_code == 200
    items = listing.json()
    assert items[0]["id"] == "session-replay"
    assert items[0]["role"] == "llm-algo"
    assert items[0]["statement_preview"] == MIND_STATEMENT[:40]
    assert detail.status_code == 200
    assert detail.content.decode("utf-8") == raw
    assert detail.text == raw


def test_write_report_loads_report_prompt_not_interviewer(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_complete(system_prompt, user_prompt, **_kwargs):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return _sample_report()

    monkeypatch.setattr("app.agent.complete_text_with_tools", fake_complete)
    text, tools = write_report(_sample_session(), _sample_turns())
    assert text == _sample_report()
    assert tools["events"] == []
    assert "终场诊断报告" in captured["system"]
    assert "整场主档" in captured["system"]
    assert "禁止默认「懂但讲不出」" in captured["system"]
    assert "只负责开场规划" not in captured["system"]
    assert "请只锁在当前方向继续深挖" not in captured["user"]
    start = captured["user"].find("{")
    end = captured["user"].rfind("}")
    context = json.loads(captured["user"][start : end + 1])
    assert context["statement"] == MIND_STATEMENT
    assert "总评" in captured["system"]


def test_write_report_falls_back_when_minimax_fails_twice(monkeypatch) -> None:
    calls = {"n": 0}

    def boom(*_args, **_kwargs):
        calls["n"] += 1
        raise LLMError("MiniMax returned an empty response")

    monkeypatch.setattr("app.agent.complete_text_with_tools", boom)
    text, tools = write_report(_sample_session(), _sample_turns())
    assert calls["n"] == 2
    assert compose_report_text(text) == text
    assert extract_primary_band(text) in {"真不懂", "项目里没有"}
    for title in REPORT_SECTION_TITLES:
        assert _has_section_title(text, title)
    assert tools["events"] == []


def test_write_report_returns_valid_report_when_sections_or_band_missing(
    monkeypatch,
) -> None:
    replies = iter(
        [
            "## 总评\n整场主档：真不懂\n只有总评",
            "## 总评\n没有主档\n\n## 岗位匹配\n对照\n\n"
            "## 知识建议\n建议\n\n## 项目改良\n改造",
        ]
    )

    def incomplete(*_args, **_kwargs):
        return next(replies)

    monkeypatch.setattr("app.agent.complete_text_with_tools", incomplete)
    text, _tools = write_report(_sample_session(), _sample_turns())
    assert compose_report_text(text) == text
    assert extract_primary_band(text) == "真不懂"
    for title in REPORT_SECTION_TITLES:
        assert _has_section_title(text, title)


def test_write_report_falls_back_on_garbage_text(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.complete_text_with_tools",
        lambda *_args, **_kwargs: "这不是报告",
    )
    text, _tools = write_report(_sample_session(), _sample_turns())
    assert compose_report_text(text) == text
    assert extract_primary_band(text) in {"真不懂", "项目里没有"}
    assert "模型未能写出合格报告" in text


def test_end_endpoint_fallback_still_saves_review(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_live_session("session-end-fallback")
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()
    def boom(*_args, **_kwargs):
        raise LLMError("MiniMax returned an empty response")

    monkeypatch.setattr("app.agent.complete_text_with_tools", boom)

    with TestClient(main_mod.app) as client:
        response = client.post("/api/sessions/session-end-fallback/end")
        assert response.status_code == 200
        body = response.text
        assert "event: done" in body
        assert "event: error" not in body
        assert "event: report_delta" in body
        assert "整场主档" in body

        stored = db.get_session("session-end-fallback")
        review = get_review("session-end-fallback")
        assert stored is not None and stored["status"] == "ended"
        assert review is not None
        assert extract_primary_band(review["report_text"]) in {"真不懂", "项目里没有"}
        detail = client.get("/api/reviews/session-end-fallback")
        assert detail.status_code == 200
        replayed = json.loads(detail.text)
        assert replayed["report"]["text"] == review["report_text"]
        live_turns = db.list_turns("session-end-fallback")
        for turn in live_turns:
            assert replayed["turns"][turn["seq"]]["body"] == turn["body"]
