"""Opening direction contract tests."""

import pytest
from pydantic import ValidationError

from app.agent import plan_directions
from app.llm import LLMError
from app.models import DirectionPlan


def valid_plan() -> dict:
    return {
        "directions": [
            {"id": "d1", "title": "输入表示", "goal": "问清 token 如何进入注意力"},
            {"id": "d2", "title": "训练流程", "goal": "问清预训练到对齐的衔接"},
            {"id": "d3", "title": "数据质量", "goal": "问清清洗规则与验证方法"},
        ],
        "first_question": "一个 token ID 进入模型后，先怎样变成 hidden state？",
    }


def test_accepts_incremental_first_question() -> None:
    plan = DirectionPlan.model_validate(valid_plan())
    assert plan.directions[0].id == "d1"


@pytest.mark.parametrize(
    "question",
    [
        "请完整介绍从 token ID 到 logits 的计算流程。",
        "请讲每一步张量 shape，并解释全部组件。",
        "这个项目做了什么？为什么这样做？",
        "先看一下 model.py:12 的实现。",
    ],
)
def test_rejects_broad_or_code_revealing_first_question(question: str) -> None:
    payload = valid_plan()
    payload["first_question"] = question
    with pytest.raises(ValidationError):
        DirectionPlan.model_validate(payload)


def test_rejects_non_sequential_direction_ids() -> None:
    payload = valid_plan()
    payload["directions"][1]["id"] = "d3"
    with pytest.raises(ValidationError):
        DirectionPlan.model_validate(payload)


def test_plan_directions_retries_invalid_first_question(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_complete(_system: str, _user: str) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            payload = valid_plan()
            payload["first_question"] = "请完整介绍从 token ID 到 logits 的计算流程。"
            return payload
        return valid_plan()

    monkeypatch.setattr("app.agent.complete_json", fake_complete)
    plan = plan_directions("复现了 RoPE、RMSNorm 与 SwiGLU。", "llm-algo")
    assert calls["n"] == 2
    assert plan.first_question.startswith("一个 token ID")


def test_plan_directions_gives_up_after_repeated_invalid_plans(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.complete_json",
        lambda *_args, **_kwargs: {
            **valid_plan(),
            "first_question": "请完整介绍 Transformer。",
        },
    )
    with pytest.raises(LLMError):
        plan_directions("复现了 RoPE。", "llm-algo")
