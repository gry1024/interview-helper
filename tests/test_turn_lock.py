"""Topic-lock and turn SSE contract tests."""

from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app import main as main_mod
from app.agent import apply_topic_lock, is_shallow_answer, run_turn
from app.models import TurnResult


DIRECTIONS = [
    {"id": "d1", "title": "输入表示", "goal": "问清 token 如何进入注意力"},
    {"id": "d2", "title": "训练流程", "goal": "问清预训练到对齐的衔接"},
    {"id": "d3", "title": "数据质量", "goal": "问清清洗规则与验证方法"},
]


def _session(*, current_direction_id: str = "d1") -> dict:
    return {
        "id": "session-lock",
        "role": "llm-algo",
        "statement": "复现了 RoPE、RMSNorm 与 SwiGLU。",
        "directions": DIRECTIONS,
        "current_direction_id": current_direction_id,
    }


def _model_turn(*, direction_done: bool, next_question: str) -> dict:
    ended = "是，因为 goal 已走完。" if direction_done else "否，因为链路还没走完。"
    return {
        "thought": (
            "评价：只复述了术语，没有讲清旋转如何作用。\n"
            "查代码：否\n"
            f"本方向结束：{ended}"
        ),
        "direction_done": direction_done,
        "next_question": next_question,
    }


def test_apply_topic_lock_stays_when_direction_is_not_done() -> None:
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=False,
        answer="我把输入到注意力的每一步都讲清楚了，包括 QKV 投影、缩放点积和输出投影，并且说明了 shape 如何对齐。",
    )
    assert done is False
    assert next_id == "d1"


def test_apply_topic_lock_advances_only_to_the_next_existing_direction() -> None:
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=True,
        answer=(
            "我已经把 token 进 embedding、再进 attention 的整条链路讲完了："
            "先查表得到向量，再做位置编码，然后进 QKV 投影和缩放点积，最后输出投影。"
        ),
    )
    assert done is True
    assert next_id == "d2"


def test_apply_topic_lock_does_not_invent_a_new_direction_at_the_end() -> None:
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d3",
        direction_done=True,
        answer=(
            "数据清洗、过滤、去重和验证都已经按 goal 问完了："
            "包括脏样本规则、长度截断、重复指令合并，以及用小批量人工抽检确认指令质量。"
            "到这里这条数据方向已经没有下一步可以挖，可以收束，不必再发明新主线。"
        ),
    )
    assert done is True
    assert next_id == "d3"
    assert next_id in {item["id"] for item in DIRECTIONS}


def test_shallow_answer_cannot_finish_a_direction() -> None:
    assert is_shallow_answer("用了 RoPE 提升外推") is True
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=True,
        answer="用了 RoPE 提升外推",
    )
    assert done is False
    assert next_id == "d1"


def test_explicitly_stuck_answer_may_finish_a_direction() -> None:
    assert is_shallow_answer("我不会，换个说法还是不知道") is False
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=True,
        answer="我不会，换个说法还是不知道",
    )
    assert done is True
    assert next_id == "d2"


def test_run_turn_overrides_model_skip_on_shallow_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.complete_json",
        lambda *_args, **_kwargs: _model_turn(
            direction_done=True,
            next_question="预训练和 SFT 之间损失怎么接？",
        ),
    )
    result, next_id = run_turn(
        session=_session(),
        turns=[
            {
                "role": "interviewer",
                "body": "一个 token ID 进入模型后，先怎样变成 hidden state？",
            }
        ],
        answer="用了 RoPE 提升外推",
    )
    assert result.direction_done is False
    assert next_id == "d1"


def test_run_turn_switches_after_a_complete_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.complete_json",
        lambda *_args, **_kwargs: _model_turn(
            direction_done=True,
            next_question="预训练和 SFT 之间损失怎么接？",
        ),
    )
    result, next_id = run_turn(
        session=_session(),
        turns=[
            {
                "role": "interviewer",
                "body": "一个 token ID 进入模型后，先怎样变成 hidden state？",
            }
        ],
        answer=(
            "我已经把 token 进 embedding、再进 attention 的整条链路讲完了："
            "先查表得到向量，再做位置编码，然后进 QKV 投影和缩放点积，最后输出投影。"
        ),
    )
    assert result.direction_done is True
    assert next_id == "d2"


def _seed_session(session_id: str = "session-sse") -> None:
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


def test_turns_endpoint_streams_required_sse_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session()
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    fake = TurnResult.model_validate(
        _model_turn(direction_done=False, next_question="RoPE 具体旋转的是哪一部分？")
    )
    monkeypatch.setattr("app.main.run_turn", lambda **_kwargs: (fake, "d1"))

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/api/sessions/session-sse/turns",
            json={"answer": "用了 RoPE 提升外推"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    body = response.text
    assert "event: thought_delta" in body
    assert "event: question" in body
    assert "event: done" in body
    assert "event: error" not in body
    assert "RoPE 具体旋转的是哪一部分？" in body


def test_ended_session_cannot_continue_turns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session("session-ended")
    with closing(db.connect()) as connection:
        connection.execute(
            "UPDATE sessions SET status = 'ended' WHERE id = ?",
            ("session-ended",),
        )
        connection.commit()
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/api/sessions/session-ended/turns",
            json={"answer": "用了 RoPE 提升外推"},
        )

    assert response.status_code == 409
