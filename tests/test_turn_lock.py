"""Topic-lock and turn SSE contract tests."""

from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app import main as main_mod
from app.agent import (
    apply_topic_lock,
    is_shallow_answer,
    is_stuck_answer,
    run_turn,
)
from app.models import TurnResult


DIRECTIONS = [
    {"id": "d1", "title": "输入表示", "goal": "问清 token 如何进入注意力"},
    {"id": "d2", "title": "训练流程", "goal": "问清预训练到对齐的衔接"},
    {"id": "d3", "title": "数据质量", "goal": "问清清洗规则与验证方法"},
]


def _session(*, current_direction_id: str = "d1", clone_ok: bool = False) -> dict:
    return {
        "id": "session-lock",
        "role": "llm-algo",
        "statement": "复现了 RoPE、RMSNorm 与 SwiGLU。",
        "directions": DIRECTIONS,
        "current_direction_id": current_direction_id,
        "clone_ok": clone_ok,
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


COMPLETE_D1 = (
    "我已经把 token 进 embedding、再进注意力的整条链路讲完了："
    "先查表得到向量，再做位置编码，然后进 QKV 投影和缩放点积，最后输出投影。"
    "到这里输入表示这条 goal 的关键步骤已经讲具体了。"
)
COMPLETE_D3 = (
    "数据清洗、过滤、去重和验证都已经按 goal 问完了："
    "包括脏样本规则、长度截断、重复指令合并，以及用小批量人工抽检确认指令质量。"
    "到这里这条数据方向已经没有下一步可以挖，可以收束，不必再发明新主线。"
)


def _history(direction_id: str, answer: str, user_turns: int = 5) -> list[dict]:
    turns = [
        {
            "role": "interviewer",
            "body": "一个 token ID 进入模型后，先怎样变成 hidden state？",
            "direction_id": direction_id,
        }
    ]
    for _ in range(user_turns):
        turns.append({"role": "user", "body": answer, "direction_id": direction_id})
        turns.append(
            {
                "role": "thought",
                "body": "评价：还在推进。\n查代码：否\n本方向结束：否，因为还没走完。",
                "direction_id": direction_id,
            }
        )
        turns.append(
            {
                "role": "interviewer",
                "body": "下一步机制是什么？",
                "direction_id": direction_id,
            }
        )
    return turns


def test_apply_topic_lock_does_not_advance_on_first_complete_answer() -> None:
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=True,
        answer=COMPLETE_D1,
    )
    assert done is False
    assert next_id == "d1"


def test_apply_topic_lock_advances_only_to_the_next_existing_direction() -> None:
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=True,
        answer=COMPLETE_D1,
        turns=_history("d1", COMPLETE_D1),
        goal="问清 token 如何进入注意力",
    )
    assert done is True
    assert next_id == "d2"


def test_apply_topic_lock_does_not_invent_a_new_direction_at_the_end() -> None:
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d3",
        direction_done=True,
        answer=COMPLETE_D3,
        turns=_history("d3", COMPLETE_D3),
        goal="问清清洗规则与验证方法",
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


def test_first_stuck_answer_cannot_finish_a_direction() -> None:
    assert is_stuck_answer("我不会，换个说法还是不知道") is True
    assert is_shallow_answer("我不会，换个说法还是不知道") is False
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=True,
        answer="我不会，换个说法还是不知道",
        turns=[
            {
                "role": "interviewer",
                "body": "一个 token ID 进入模型后，先怎样变成 hidden state？",
                "direction_id": "d1",
            }
        ],
        goal="问清 token 如何进入注意力",
    )
    assert done is False
    assert next_id == "d1"


def test_second_stuck_after_rephrase_may_finish_a_direction() -> None:
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=True,
        answer="我还是不会，换个说法还是不知道",
        turns=[
            {
                "role": "interviewer",
                "body": "一个 token ID 进入模型后，先怎样变成 hidden state？",
                "direction_id": "d1",
            },
            {
                "role": "user",
                "body": "这块我不太懂",
                "direction_id": "d1",
            },
            {
                "role": "thought",
                "body": "评价：空白。\n查代码：否\n本方向结束：否，因为要换说法。",
                "direction_id": "d1",
            },
            {
                "role": "interviewer",
                "body": "换个说法：整数编号怎么变成向量？",
                "direction_id": "d1",
            },
        ],
        goal="问清 token 如何进入注意力",
    )
    assert done is True
    assert next_id == "d2"


def _fake_library(n: int = 2):
    hits = [
        {
            "id": f"iv-{index}",
            "kind": "interview",
            "company": "测试",
            "role": "算法",
            "source": "小红书",
            "url": "https://example.com",
            "snippet": f"RoPE 原问 {index}",
        }
        for index in range(n)
    ]

    class Result:
        def for_model(self) -> str:
            return f"命中 {n} 条"

        def for_public(self) -> str:
            return f"检索到 {n} 条相关面经" if n else "没有检索到与当前话题相关的面经"

        def public_hits(self) -> list[dict[str, str]]:
            return hits

    return Result()


def test_run_turn_overrides_model_skip_on_shallow_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.complete_json_with_tools",
        lambda *_args, **_kwargs: _model_turn(
            direction_done=True,
            next_question="预训练和 SFT 之间损失怎么接？",
        ),
    )
    monkeypatch.setattr(
        "app.agent.run_search_library_from_tool_args",
        lambda *_args, **_kwargs: _fake_library(2),
    )
    result, next_id, tools = run_turn(
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
    search_events = [event for event in tools["events"] if event["name"] == "search_library"]
    assert len(search_events) == 1
    assert len(search_events[0]["hits"]) == 2
    assert "检索面经：" not in result.thought
    assert "条真实问法" not in result.thought


def test_run_turn_keeps_direction_after_first_complete_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.complete_json_with_tools",
        lambda *_args, **_kwargs: _model_turn(
            direction_done=True,
            next_question="预训练和 SFT 之间损失怎么接？",
        ),
    )
    monkeypatch.setattr(
        "app.agent.run_search_library_from_tool_args",
        lambda *_args, **_kwargs: _fake_library(2),
    )
    result, next_id, tools = run_turn(
        session=_session(),
        turns=[
            {
                "role": "interviewer",
                "body": "一个 token ID 进入模型后，先怎样变成 hidden state？",
                "direction_id": "d1",
            }
        ],
        answer=COMPLETE_D1,
    )
    assert result.direction_done is False
    assert next_id == "d1"
    assert "不要跳到别的方向" in result.next_question
    assert any(event["name"] == "search_library" for event in tools["events"])


def test_run_turn_switches_after_enough_complete_answers(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.complete_json_with_tools",
        lambda *_args, **_kwargs: _model_turn(
            direction_done=True,
            next_question="预训练和 SFT 之间损失怎么接？",
        ),
    )
    monkeypatch.setattr(
        "app.agent.run_search_library_from_tool_args",
        lambda *_args, **_kwargs: _fake_library(0),
    )
    result, next_id, tools = run_turn(
        session=_session(),
        turns=_history("d1", COMPLETE_D1),
        answer=COMPLETE_D1,
    )
    assert result.direction_done is True
    assert next_id == "d2"
    search_events = [event for event in tools["events"] if event["name"] == "search_library"]
    assert search_events
    assert search_events[0]["hits"] == []


def test_apply_topic_lock_stays_when_goal_checkpoints_are_missing() -> None:
    off_topic = (
        "我花了很多时间和同学讨论过训练稳定性，也写了实验笔记，"
        "还对比过几种学习率，但没有碰到你问的那一步具体机制。"
    )
    done, next_id = apply_topic_lock(
        directions=DIRECTIONS,
        current_direction_id="d1",
        direction_done=True,
        answer=off_topic,
        turns=_history("d1", off_topic),
        goal="问清 token 如何进入注意力",
    )
    assert done is False
    assert next_id == "d1"


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
    monkeypatch.setattr(
        "app.main.run_turn",
        lambda **_kwargs: (fake, "d1", {"events": [], "meta": []}),
    )

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
    thought_events = [part for part in body.split("\n\n") if "event: thought_delta" in part]
    assert len(thought_events) >= 2


def test_turns_endpoint_can_stream_tool_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session("session-sse-tool")
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    fake = TurnResult.model_validate(
        _model_turn(direction_done=False, next_question="RoPE 具体旋转的是哪一部分？")
    )
    public = "仓库未体现这些实现陈述：rerank、万卡。追问只谈能力与证据，不要点名文件或行号。"
    model_text = "ok=true\nconclusion=仓库中未体现：rerank、万卡。\ninternal_excerpt:\nmodel.py:12"
    monkeypatch.setattr(
        "app.main.run_turn",
        lambda **_kwargs: (
            fake,
            "d1",
            {
                "events": [
                    {
                        "name": "code_inspect",
                        "args": {"query": "rerank 万卡"},
                        "result": public,
                    }
                ],
                "meta": [
                    {
                        "name": "code_inspect",
                        "args": {"query": "rerank 万卡"},
                        "result": model_text,
                    }
                ],
            },
        ),
    )

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/api/sessions/session-sse-tool/turns",
            json={"answer": "我还做了 rerank 和分布式万卡训练"},
        )

    assert response.status_code == 200
    body = response.text
    assert "event: tool" in body
    assert "event: thought_delta" in body
    assert "event: question" in body
    assert "code_inspect" in body
    assert "仓库未体现" in body
    assert "RoPE 具体旋转的是哪一部分？" in body
    assert "model.py:12" not in body.split("event: question")[-1]

    turns = db.list_turns("session-sse-tool")
    thought = next(item for item in turns if item["role"] == "thought")
    assert thought["meta"][0]["name"] == "code_inspect"
    assert "internal_excerpt" in thought["meta"][0]["result"]


def test_turns_endpoint_emits_tool_start_before_thought(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session("session-sse-progress")
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    fake = TurnResult.model_validate(
        _model_turn(direction_done=False, next_question="RoPE 具体旋转的是哪一部分？")
    )

    def _fake_run_turn(**kwargs):
        on_progress = kwargs.get("on_progress")
        event = {
            "name": "search_library",
            "args": {"query": "RoPE"},
            "result": "检索到 5 条面经",
        }
        if on_progress:
            on_progress({"kind": "tool_start", "name": "search_library"})
            on_progress({"kind": "tool", "event": event})
            on_progress({"kind": "thought_delta", "text": "评价：先看机制。\n"})
            on_progress({"kind": "thought_delta", "text": "查代码：否\n"})
            on_progress({"kind": "thought_delta", "text": "本方向结束：否"})
        return fake, "d1", {"events": [event], "meta": [event]}

    monkeypatch.setattr("app.main.run_turn", _fake_run_turn)

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/api/sessions/session-sse-progress/turns",
            json={"answer": "用了 RoPE 提升外推"},
        )

    assert response.status_code == 200
    body = response.text
    assert "event: tool_start" in body
    assert "正在调用检索面经工具" in body
    assert "检索到 5 条面经" in body
    start_at = body.find("event: tool_start")
    thought_at = body.find("event: thought_delta")
    question_at = body.find("event: question")
    assert 0 <= start_at < thought_at < question_at
    assert body.count("检索到 5 条面经") == 1
    assert "检索面经：项目总览" not in body
    assert "查代码：是（search_library）" not in body


def test_unknown_tool_is_not_recorded(monkeypatch) -> None:
    from app.agent import resolve_tool_name

    assert resolve_tool_name("thought") is None
    assert resolve_tool_name("search_library") == "search_library"
    assert resolve_tool_name("检索面经") == "search_library"

    captured: dict[str, object] = {}

    def fake_complete(system, user, tools, run_tool, max_tool_rounds=2, **_kwargs):
        captured["reply"] = run_tool("thought", {})
        return _model_turn(direction_done=False, next_question="RoPE 具体旋转的是哪一部分？")

    monkeypatch.setattr("app.agent.complete_json_with_tools", fake_complete)
    monkeypatch.setattr(
        "app.agent.run_search_library_from_tool_args",
        lambda *_args, **_kwargs: type(
            "R",
            (),
            {
                "for_model": lambda self: "命中",
                "for_public": lambda self: "检索到 1 条面经",
                "public_hits": lambda self: [
                    {
                        "id": "iv-1",
                        "kind": "interview",
                        "company": "测试",
                        "role": "算法",
                        "source": "小红书",
                        "url": "https://example.com",
                        "snippet": "RoPE 怎么外推？",
                    }
                ],
            },
        )(),
    )
    result, _next_id, tools = run_turn(
        session=_session(),
        turns=_history("d1", "用了 RoPE"),
        answer="用了 RoPE 提升外推，旋转的是 Q 和 K。",
    )
    assert "只能使用" in str(captured["reply"])
    assert all(event.get("name") != "thought" for event in tools["events"])
    assert "未知 tool" not in result.thought


def test_turns_endpoint_includes_search_hits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    db.init_db()
    _seed_session("session-sse-hits")
    main_mod._write_requests.clear()
    main_mod._active_turns.clear()

    fake = TurnResult.model_validate(
        _model_turn(direction_done=False, next_question="RoPE 具体旋转的是哪一部分？")
    )
    hits = [
        {
            "id": "iv-rope",
            "kind": "interview",
            "company": "月之暗面",
            "role": "LLM 算法",
            "source": "小红书",
            "url": "https://example.com/x",
            "snippet": "RoPE 外推怎么做？",
        }
    ]

    def _fake_run_turn(**kwargs):
        event = {
            "name": "search_library",
            "args": {"query": "RoPE"},
            "result": "检索到 1 条面经",
            "hits": hits,
        }
        on_progress = kwargs.get("on_progress")
        if on_progress:
            on_progress({"kind": "tool_start", "name": "search_library"})
            on_progress({"kind": "tool", "event": event})
        return fake, "d1", {"events": [event], "meta": [event]}

    monkeypatch.setattr("app.main.run_turn", _fake_run_turn)

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/api/sessions/session-sse-hits/turns",
            json={"answer": "用了 RoPE 提升外推"},
        )
        snapshot = client.get("/api/sessions/session-sse-hits")

    assert response.status_code == 200
    assert "RoPE 外推怎么做？" in response.text
    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["pending"] is False
    assert payload["session"]["id"] == "session-sse-hits"
    user_turns = [item for item in payload["turns"] if item["role"] == "user"]
    assert user_turns[-1]["body"] == "用了 RoPE 提升外推"


def test_turn_result_allows_torch_compile_in_next_question() -> None:
    question = "那你跟 torch.compile 比，手写 Triton 的延迟你怎么权衡？"
    result = TurnResult.model_validate(
        {
            "thought": "评价：还停在收益数字。\n查代码：否\n本方向结束：否，因为融合 kernel 还没问完。",
            "direction_done": False,
            "next_question": question,
        }
    )
    assert result.next_question == question


def test_turn_result_rejects_filename_line_in_next_question() -> None:
    from pydantic import ValidationError

    try:
        TurnResult.model_validate(
            {
                "thought": "评价：虚。\n查代码：是\n本方向结束：否，因为还在当前方向。",
                "direction_done": False,
                "next_question": "请看 model.py:12 的 RoPE 实现？",
            }
        )
    except ValidationError as exc:
        assert "文件名或行号" in str(exc)
    else:
        raise AssertionError("next_question with coordinates must be rejected")


def test_turn_result_allows_a_longer_but_single_next_question() -> None:
    question = "整数 token 先变成向量时，这个映射表的参数是学出来的吗？"
    result = TurnResult.model_validate(
        {
            "thought": "评价：仍停在术语层。\n查代码：否\n本方向结束：否，因为 embedding 还没问到。",
            "direction_done": False,
            "next_question": question,
        }
    )
    assert result.next_question == question


def test_turn_result_rejects_piled_or_double_next_question() -> None:
    from pydantic import ValidationError

    for question in (
        "QKV 分别来自哪？缩放又为什么除根号 d_k？",
        "请分别讲清 QKV 来源以及 scaled 的原因？",
    ):
        try:
            TurnResult.model_validate(
                {
                    "thought": "评价：虚。\n查代码：否\n本方向结束：否，因为还在当前方向。",
                    "direction_done": False,
                    "next_question": question,
                }
            )
        except ValidationError:
            continue
        raise AssertionError(f"broad question must be rejected: {question}")


def test_coerce_empty_or_compound_next_question_still_replies() -> None:
    from app.agent import coerce_turn_payload, fallback_turn_result

    direction = DIRECTIONS[0]
    empty = TurnResult.model_validate(
        coerce_turn_payload(
            {
                "thought": "评价：先接住这一答。\n查代码：否\n本方向结束：否，因为还在当前方向。",
                "direction_done": False,
                "next_question": "",
            },
            direction=direction,
            answer="旋的是 Q 和 K。",
        )
    )
    assert empty.next_question
    assert "评价" in empty.thought
    compound = TurnResult.model_validate(
        coerce_turn_payload(
            {
                "thought": "评价：机制还虚。\n查代码：否",
                "direction_done": False,
                "next_question": "QKV 分别来自哪？缩放又为什么除根号 d_k？",
            },
            direction=direction,
            answer="旋的是 Q 和 K。",
        )
    )
    assert compound.next_question.count("？") + compound.next_question.count("?") <= 1
    echo = TurnResult.model_validate(
        coerce_turn_payload(
            {
                "thought": "评价：先接住。",
                "direction_done": False,
                "next_question": "下一问必须只问一个微步骤？分别讲清 Q 和 K？",
            },
            direction=direction,
            answer="旋的是 Q 和 K。",
        )
    )
    assert echo.next_question
    assert "微步骤" not in echo.next_question
    fallback = fallback_turn_result(direction, "用了 RoPE")
    assert fallback.next_question
    assert "评价" in fallback.thought


def test_run_turn_falls_back_when_llm_never_returns_json(monkeypatch) -> None:
    from app.llm import LLMError

    def boom(*_args, **_kwargs):
        raise LLMError("MiniMax returned an empty response")

    monkeypatch.setattr("app.agent.complete_json_with_tools", boom)
    monkeypatch.setattr(
        "app.agent.run_search_library_from_tool_args",
        lambda *_args, **_kwargs: _fake_library(0),
    )
    result, next_id, _tools = run_turn(
        session=_session(),
        turns=[
            {
                "role": "interviewer",
                "body": "RoPE 具体旋转的是哪一部分？",
                "direction_id": "d1",
            }
        ],
        answer="请继续问吧",
    )
    assert next_id == "d1"
    assert result.next_question
    assert "评价" in result.thought
    assert "本方向结束" in result.thought


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
