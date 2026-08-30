"""Catalog lookup for sourced hand-write exercises."""

from __future__ import annotations

import json
from pathlib import Path

from app.tools.code_exercise import (
    ERROR_DUPLICATE,
    ERROR_NO_TOPIC_MATCH,
    ERROR_ONE_PER_TURN,
    ERROR_UNKNOWN_ID,
    catalog_for_prompt,
    get_exercise,
    load_exercises,
    match_exercise,
    resolve_exercise,
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
    assert unrelated.error == ERROR_NO_TOPIC_MATCH


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


def test_get_exercise_returns_none_for_unknown() -> None:
    assert get_exercise("mha-forward") is not None
    assert get_exercise("not-in-bank") is None
