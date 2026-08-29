"""Session persistence round-trip tests."""

from pathlib import Path

from app import db


def test_session_roundtrip_preserves_plan_and_statement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "app.db"
    monkeypatch.setattr(db, "DB_PATH", database_path)
    db.init_db()

    directions = [
        {"id": "d1", "title": "架构", "goal": "问清输入到注意力"},
        {"id": "d2", "title": "训练", "goal": "问清训练阶段衔接"},
        {"id": "d3", "title": "数据", "goal": "问清数据质量验证"},
    ]
    statement = "保留换行和原文：\nRoPE / RMSNorm / SwiGLU"
    db.create_session(
        session_id="session-1",
        github_url="https://github.com/owner/repo",
        statement=statement,
        role="llm-algo",
        directions=directions,
        clone_path=None,
        clone_ok=False,
        first_question="一个 token ID 先如何变成向量？",
    )

    session = db.get_session("session-1")
    assert session is not None
    assert session["statement"] == statement
    assert session["directions"] == directions
    assert session["current_direction_id"] == "d1"
    assert session["clone_ok"] is False
    assert session["status"] == "live"
