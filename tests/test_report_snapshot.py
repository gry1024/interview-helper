"""Pure-function tests for end-moment snapshot and read-only replay."""

import json

import pytest

from app import report


MIND_STATEMENT = (
    "MiniMind:全链路轻量级大语言模型复现与训练：为深入探究LLM内部机制，"
    "复现了一个类LLaMA架构的轻量级语言模型 (Decoder-only)，涵盖从 Tokenizer训练、"
    "预训练(Pre-train)、指令微调(SFT)到DPO对齐的完整流水线。核心工作: "
    "基于PyTorch复现了LLaMA的核心组件，包括RoPE旋转位置编码（提升外推性) "
    "RMSNorm(优化收敛速度)及SwiGLU激活函数， 深入掌握了 Transformer的底层计算细节。"
    "构建并清洗中文指令数据集，设计 Prompt Template，成功跑通了从无监督预训练到"
    "指令跟随的完整训练闭环。\n保留换行与引号：\"RoPE\" / RMSNorm / SwiGLU"
)

LONG_THOUGHT = (
    "评价：只报了组件名字，没有把 token 进注意力的路径讲完。"
    "换说法后仍停在「用了 RoPE 提升外推」，公式和缓存都没接上。\n"
    "查代码：是。对照陈述里的 RoPE / RMSNorm / SwiGLU；"
    "回答里的「rerank / 分布式万卡训练」仓库侧未作为本项目主线出现。\n"
    "本方向结束：否，因为输入到注意力的链路还没问完。\n"
    + ("这句必须完整进 snapshot，禁止省略。" * 40)
)


def _sample_session() -> dict:
    return {
        "id": "session-minimind",
        "created_at": "2026-08-30T03:00:00+00:00",
        "github_url": "https://github.com/jingyaogong/minimind.git",
        "statement": MIND_STATEMENT,
        "role": "llm-algo",
        "directions": [
            {"id": "d1", "title": "架构组件", "goal": "从输入问到注意力输出"},
            {"id": "d2", "title": "训练流水线", "goal": "问清预训练到 DPO 的衔接"},
            {"id": "d3", "title": "数据与指令", "goal": "问清清洗与模板如何验证"},
        ],
        "current_direction_id": "d1",
        "clone_path": "repos/session-minimind",
        "clone_ok": True,
        "status": "live",
        "first_question": "一个 token ID 进入模型后，先怎样变成 hidden state？",
    }


def _sample_turns() -> list[dict]:
    session_id = "session-minimind"
    return [
        {
            "id": 1,
            "session_id": session_id,
            "seq": 0,
            "role": "interviewer",
            "body": "一个 token ID 进入模型后，先怎样变成 hidden state？",
            "direction_id": "d1",
            "meta": None,
        },
        {
            "id": 2,
            "session_id": session_id,
            "seq": 1,
            "role": "user",
            "body": "用了 RoPE 提升外推，另外我做了 rerank 和万卡分布式。",
            "direction_id": "d1",
            "meta": None,
        },
        {
            "id": 3,
            "session_id": session_id,
            "seq": 2,
            "role": "thought",
            "body": LONG_THOUGHT,
            "direction_id": "d1",
            "meta": [
                {
                    "name": "code_inspect",
                    "args": {"query": "rerank 万卡"},
                    "result": "未把 rerank / 万卡分布式训练写成主线实现。",
                }
            ],
        },
        {
            "id": 4,
            "session_id": session_id,
            "seq": 3,
            "role": "interviewer",
            "body": "先别管分布式。这个 token 的向量接下来怎么进注意力？",
            "direction_id": "d1",
            "meta": None,
        },
    ]


def _sample_report() -> str:
    return report.build_report_from_parts(
        overall=(
            "整场主档：懂但讲不出\n"
            "整场偏「懂但讲不出」，RoPE 名字在、机制不在；"
            "「rerank / 万卡」落在「项目里没有」。\n"
            "真懂：无。懂但讲不出：位置编码为什么要旋转。"
            "真不懂：hidden state 之后如何进 attention。"
            "项目里没有：分布式万卡与 rerank。"
        ),
        job_essence_compare=(
            "岗位本质要沿数据流解释机制，不只要组件名。"
            "本项目陈述覆盖 Tokenizer / 预训练 / SFT / DPO，"
            "口头还没走到注意力，价值在训练闭环而不在检索。"
        ),
        knowledge_advice=(
            "用 MiniMind 自己的输入把「token ID → 向量 → 注意力」讲成一条链，"
            "不要只说「用了 RoPE」。"
        ),
        project_improve=(
            "几小时内补一个「有/无 RoPE」的短对照，写下外推是否变稳，"
            "不要新开 rerank 项目。"
        ),
    )


def test_snapshot_keeps_full_session_turns_and_report_text() -> None:
    session = _sample_session()
    turns = _sample_turns()
    report_text = _sample_report()

    snapshot = report.assemble_review_snapshot(session, turns, report_text)
    dumped = report.snapshot_to_json(snapshot)
    payload = json.loads(dumped)

    assert session["status"] == "live"
    assert snapshot.session.status == "ended"
    assert snapshot.session.statement == MIND_STATEMENT
    assert snapshot.report.text == report_text
    assert payload["session"]["statement"] == MIND_STATEMENT
    assert payload["report"]["text"] == report_text
    assert payload["turns"][2]["body"] == LONG_THOUGHT
    assert payload["turns"][2]["meta"][0]["result"] == (
        "未把 rerank / 万卡分布式训练写成主线实现。"
    )
    for turn in turns:
        assert snapshot.turns[turn["seq"]].body == turn["body"]
        assert payload["turns"][turn["seq"]]["body"] == turn["body"]
    assert not report.thoughts_leak_report_content(turns)
    context = json.loads(report.build_end_report_context(session, turns))
    assert context["statement"] == MIND_STATEMENT
    for turn in turns:
        assert context["turns"][turn["seq"]]["body"] == turn["body"]


def test_load_review_for_replay_does_not_call_generators(monkeypatch) -> None:
    report_text = _sample_report()
    raw = report.dump_end_snapshot(_sample_session(), _sample_turns(), report_text)

    def forbid(name: str):
        def _raise(*_args, **_kwargs):
            raise AssertionError(f"复盘读取不得调用 {name} 改写")

        return _raise

    monkeypatch.setattr(report, "build_report_from_parts", forbid("build_report_from_parts"))
    monkeypatch.setattr(report, "compose_report_text", forbid("compose_report_text"))
    monkeypatch.setattr(
        report, "assemble_review_snapshot", forbid("assemble_review_snapshot")
    )
    monkeypatch.setattr(report, "dump_end_snapshot", forbid("dump_end_snapshot"))
    monkeypatch.setattr(
        report, "build_end_report_context", forbid("build_end_report_context")
    )

    loaded = report.load_review_for_replay(raw)
    assert loaded.report.text == report_text
    assert loaded.session.statement == MIND_STATEMENT
    assert loaded.turns[2].body == LONG_THOUGHT
    assert report.snapshot_to_json(loaded) == raw


def test_compose_report_text_keeps_verbatim_and_rejects_missing_section() -> None:
    report_text = _sample_report()
    assert report.compose_report_text(report_text) is report_text
    with pytest.raises(ValueError, match="岗位本质对照"):
        report.compose_report_text("## 总评\n整场主档：真不懂\n只有总评")
    with pytest.raises(ValueError, match="整场主档"):
        report.compose_report_text(
            "## 总评\n没有主档\n\n## 岗位本质对照\n对照\n\n"
            "## 知识建议\n建议\n\n## 项目改良\n改造"
        )
