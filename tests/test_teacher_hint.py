"""Teacher side-hint: inspect optional, recorded for the end report."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.models import TeacherHintResult
from app.report import assemble_review_snapshot, build_end_report_context
from app.teacher import write_teacher_hint


def _session() -> dict:
    return {
        "id": "hint-session",
        "role": "llm-algo",
        "statement": "复现了 RoPE。",
        "current_direction_id": "d1",
        "clone_ok": True,
        "directions": [{"id": "d1", "title": "输入", "goal": "问清 embedding"}],
        "created_at": "2026-08-30T00:00:00+00:00",
        "github_url": "https://github.com/jingyaogong/minimind.git",
        "clone_path": None,
        "status": "live",
        "first_question": "token 怎么变成向量？",
    }


def test_teacher_hint_contract_rejects_coordinates() -> None:
    try:
        TeacherHintResult.model_validate(
            {"hint": "请看 model.py:12 的实现。这只是提示，请用自己的话回答面试官。", "looked_at_code": True}
        )
    except Exception as exc:
        assert "文件名或行号" in str(exc)
        return
    raise AssertionError("coordinates in teacher hint must fail")


def test_write_teacher_hint_may_call_inspect(monkeypatch) -> None:
    seen: list[str] = []

    def fake_complete(system, user, tools, run_tool):
        seen.append("complete")
        inspect_text = run_tool("code_inspect", {"query": "RoPE"})
        assert "RoPE" in inspect_text or inspect_text
        return {
            "hint": "位置编码加在 Q/K 上。这只是提示，请用自己的话回答面试官。",
            "looked_at_code": True,
        }

    monkeypatch.setattr("app.teacher.complete_json_with_tools", fake_complete)
    monkeypatch.setattr(
        "app.teacher.run_code_inspect_from_tool_args",
        lambda *_args, **_kwargs: type(
            "R",
            (),
            {
                "for_model": lambda self: "ok=true conclusion=有 RoPE",
                "for_public": lambda self: "仓库能对上 RoPE",
            },
        )(),
    )
    result, bundle = write_teacher_hint(
        session=_session(),
        turns=[{"role": "interviewer", "body": "RoPE 加在哪一部分？"}],
    )
    assert "自己的话" in result.hint
    assert result.looked_at_code is True
    assert bundle["events"][0]["name"] == "code_inspect"
    assert seen == ["complete"]


def test_help_is_recorded_and_frozen_in_snapshot(tmp_path: Path) -> None:
    monkeypatch_db = tmp_path / "app.db"
    db.DB_PATH = monkeypatch_db
    db.init_db()
    db.create_session(
        session_id="s1",
        github_url="https://github.com/jingyaogong/minimind.git",
        statement="MiniMind",
        role="llm-algo",
        directions=[{"id": "d1", "title": "输入", "goal": "embedding"}],
        clone_path=None,
        clone_ok=False,
        first_question="token 怎么变成向量？",
    )
    record = db.append_help(
        session_id="s1",
        question="token 怎么变成向量？",
        hint="先查 embedding 表。这只是提示，请用自己的话回答面试官。",
        looked_at_code=False,
        inspect_public=None,
        direction_id="d1",
    )
    helps = db.list_helps("s1")
    assert len(helps) == 1
    assert helps[0]["id"] == record["id"]
    session = db.get_session("s1")
    turns = db.list_turns("s1")
    context = build_end_report_context(session, turns, helps)
    assert "help_count" in context
    assert '"help_count":1' in context
    snapshot = assemble_review_snapshot(
        session,
        turns,
        "## 总评\n\n整场主档：懂但讲不出\n\n## 岗位本质对照\n\na\n\n## 知识建议\n\nb\n\n## 项目改良\n\nc",
        helps,
    )
    assert snapshot.helps[0].question == "token 怎么变成向量？"
    assert snapshot.helps[0].hint.startswith("先查")


def test_hint_route_rejects_missing_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    with TestClient(app) as client:
        response = client.post("/api/sessions/missing/hints", json={})
    assert response.status_code == 404
