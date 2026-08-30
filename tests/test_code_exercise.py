"""Catalog lookup for sourced hand-write exercises."""

from __future__ import annotations

import json
from pathlib import Path

from app.tools.code_exercise import (
    ERROR_DUPLICATE,
    ERROR_NO_TOPIC_MATCH,
    ERROR_ONE_PER_TURN,
    ERROR_UNKNOWN_ID,
    ERROR_UNRELATED_ALGO,
    catalog_for_prompt,
    get_exercise,
    load_exercises,
    match_exercise,
    match_implementation_exercise,
    resolve_exercise,
    successful_opened_exercise_ids,
    used_exercise_ids,
)


JD_DIR = Path(__file__).resolve().parent.parent / "app" / "jd"


def _sample_ids() -> set[str]:
    ids: set[str] = set()
    for filename in ("interviews.json", "jds.json"):
        samples = json.loads((JD_DIR / filename).read_text(encoding="utf-8"))
        ids.update(str(item.get("id")) for item in samples if item.get("id"))
    return ids


def test_bank_has_sourced_python_exercises() -> None:
    exercises = load_exercises()
    assert 8 <= len(exercises) <= 15
    known = _sample_ids()
    ids = [item.id for item in exercises]
    assert len(ids) == len(set(ids))
    for exercise in exercises:
        assert exercise.language == "python"
        assert exercise.prompt
        assert exercise.starter
        assert exercise.source_ids
        assert exercise.topics
        assert set(exercise.source_ids) <= known


def test_catalog_lists_ids_without_inventing() -> None:
    catalog = catalog_for_prompt()
    assert "mha-forward" in catalog
    assert "rope-apply" in catalog
    assert "禁止编题" in catalog
    one = catalog_for_prompt("mha-forward")
    assert "mha-forward" in one
    assert "rope-apply" not in one


def test_resolve_by_id_and_topic() -> None:
    by_id = resolve_exercise({"exercise_id": "mha-forward"})
    assert by_id.ok and by_id.exercise is not None
    assert by_id.exercise.id == "mha-forward"
    assert by_id.sse_payload()["language"] == "python"
    assert "Multi-Head" in by_id.sse_payload()["title"]

    by_topic = match_exercise("Transformer Multi-Head Attention")
    assert by_topic is not None
    assert by_topic.id == "mha-forward"
    assert match_exercise("RoPE") is not None
    assert match_exercise("RoPE").id == "rope-apply"
    assert match_exercise("KV cache") is not None
    assert match_exercise("KV cache").id == "kv-cache-step"
    assert match_exercise("LoRA rank") is not None
    assert match_exercise("LoRA rank").id == "lora-linear"


def test_reject_invented_or_unrelated_topics() -> None:
    unknown = resolve_exercise({"exercise_id": "two-sum-leetcode"})
    assert unknown.ok is False
    assert unknown.error == ERROR_UNKNOWN_ID
    assert unknown.sse_payload() is None

    unrelated = resolve_exercise({"topic": "反转链表与背包问题"})
    assert unrelated.ok is False
    assert unrelated.error == ERROR_UNRELATED_ALGO
    assert unrelated.sse_payload() is None


def test_same_exercise_not_repeated_and_one_per_turn() -> None:
    used = resolve_exercise(
        {"exercise_id": "mha-forward"},
        used_ids={"mha-forward"},
    )
    assert used.ok is False
    assert used.error == ERROR_DUPLICATE

    second = resolve_exercise(
        {"exercise_id": "rope-apply"},
        already_opened_this_turn=True,
    )
    assert second.ok is False
    assert second.error == ERROR_ONE_PER_TURN


def test_used_exercise_ids_from_turn_meta() -> None:
    turns = [
        {
            "role": "thought",
            "meta": [
                {
                    "name": "code_exercise",
                    "args": {"exercise_id": "mha-forward"},
                    "exercise_id": "mha-forward",
                }
            ],
        },
        {
            "role": "user",
            "meta": {"kind": "code_submission", "exercise_id": "rope-apply"},
        },
    ]
    assert used_exercise_ids(turns) == {"mha-forward", "rope-apply"}
    assert successful_opened_exercise_ids(turns) == {"rope-apply"}
    with_payload = [
        {
            "role": "thought",
            "meta": [
                {
                    "name": "code_exercise",
                    "args": {"exercise_id": "mha-forward"},
                    "exercise_id": "mha-forward",
                    "result": "已打开《手撕 Multi-Head Attention》",
                    "payload": {
                        "exercise_id": "mha-forward",
                        "title": "手撕 Multi-Head Attention",
                        "prompt": "写出前向",
                        "starter": "pass\n",
                    },
                }
            ],
        }
    ]
    assert successful_opened_exercise_ids(with_payload) == {"mha-forward"}


def test_get_exercise_returns_none_for_unknown() -> None:
    assert get_exercise("mha-forward") is not None
    assert get_exercise("not-in-bank") is None


def test_match_implementation_opens_rope_not_transformer_name_drop() -> None:
    rope = match_implementation_exercise(
        recent_text="RoPE 具体旋转的是哪一部分？",
        current_text="旋的是 Q 和 K，把偶数维两两组成复数再乘旋转矩阵。",
        used_ids=set(),
    )
    assert rope is not None
    assert rope.id == "rope-apply"
    named = match_implementation_exercise(
        recent_text="你项目用了什么结构？",
        current_text="用了 Transformer。",
        used_ids=set(),
    )
    assert named is None
    skipped = match_implementation_exercise(
        recent_text="RoPE 具体旋转的是哪一部分？",
        current_text="请继续问吧",
        used_ids=set(),
    )
    assert skipped is None


def test_interview_sourced_handwrite_opens_with_sample_id() -> None:
    rope = resolve_exercise({"topic": "RoPE"})
    assert rope.ok and rope.exercise is not None
    assert rope.exercise.id == "rope-apply"
    assert rope.sse_payload()["sample_id"]

    mha = resolve_exercise({"topic": "Multi-Head Attention"})
    assert mha.ok and mha.exercise is not None
    assert mha.exercise.id == "mha-forward"

    entropy = resolve_exercise({"topic": "交叉熵"})
    assert entropy.ok and entropy.exercise is not None
    payload = entropy.sse_payload() or {}
    assert payload.get("sample_id")
    assert "原问" in (entropy.exercise.prompt or "")
    assert entropy.exercise.starter
    assert entropy.exercise.language == "python"


def test_unrelated_algo_and_unmentioned_topic_stay_oral() -> None:
    linked = resolve_exercise({"topic": "反转链表"})
    assert linked.ok is False
    assert linked.sse_payload() is None
    assert linked.error in {ERROR_UNRELATED_ALGO, ERROR_NO_TOPIC_MATCH}

    missing = resolve_exercise({"topic": "量子比特纠缠门分解"})
    assert missing.ok is False
    assert missing.error == ERROR_NO_TOPIC_MATCH
    assert missing.sse_payload() is None
