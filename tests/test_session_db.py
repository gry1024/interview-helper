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

    opening = db.list_turns("session-1")
    assert len(opening) == 1
    assert opening[0]["seq"] == 0
    assert opening[0]["role"] == "interviewer"
    assert opening[0]["body"] == "一个 token ID 先如何变成向量？"
    assert opening[0]["direction_id"] == "d1"
    assert opening[0]["meta"] is None


def test_append_turn_bundle_keeps_full_text_and_can_switch_direction(
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
    thought = "评价：把输入到注意力讲清楚了。\n查代码：否\n本方向结束：是，因为 goal 已走完。"
    next_question = "预训练和 SFT 之间，损失和数据分别怎么接？"
    db.create_session(
        session_id="session-2",
        github_url="https://github.com/owner/repo",
        statement="原文必须完整保留",
        role="llm-algo",
        directions=directions,
        clone_path=None,
        clone_ok=False,
        first_question="一个 token ID 先如何变成向量？",
    )
    db.append_turn_bundle(
        session_id="session-2",
        user_answer="从 embedding 进到 attention 后再投影输出。",
        thought=thought,
        next_question=next_question,
        direction_id="d1",
        next_direction_id="d2",
        meta=None,
    )

    session = db.get_session("session-2")
    assert session is not None
    assert session["current_direction_id"] == "d2"

    turns = db.list_turns("session-2")
    assert [turn["seq"] for turn in turns] == [0, 1, 2, 3]
    assert [turn["role"] for turn in turns] == [
        "interviewer",
        "user",
        "thought",
        "interviewer",
    ]
    assert turns[1]["body"] == "从 embedding 进到 attention 后再投影输出。"
    assert turns[2]["body"] == thought
    assert turns[3]["body"] == next_question
    assert turns[3]["direction_id"] == "d2"
