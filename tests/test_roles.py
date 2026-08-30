"""Role catalog is the single source for supported interview jobs."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.models import SessionCreate
from app.roles import (
    allowed_role_ids,
    all_role_stats,
    assign_sample_role,
    load_library_samples,
    load_role_prompt,
    role_label,
)
from app.tools import INTERVIEW_TURN_TOOLS
from app.main import app


def test_catalog_keeps_three_distinct_roles() -> None:
    ids = allowed_role_ids()
    assert ids == ("llm-algo", "agent", "rag")
    assert "training" not in ids
    assert role_label("llm-algo") == "LLM 算法实习"
    assert role_label("agent") == "Agent 应用实习"
    assert role_label("rag") == "RAG / AI 搜索实习"


def test_every_library_sample_is_assigned() -> None:
    jds, interviews = load_library_samples()
    stats = {item["id"]: item for item in all_role_stats()}
    assert sum(item["jd_count"] for item in stats.values()) == len(jds)
    assert sum(item["interview_count"] for item in stats.values()) == len(interviews)
    for role_id, item in stats.items():
        assert item["jd_count"] >= 4, role_id
        assert item["interview_count"] >= 16, role_id
        prompt = load_role_prompt(role_id)
        assert f"覆盖 JD {item['jd_count']} 条" in prompt
        for sample_id in item["sample_ids"][:8]:
            assert sample_id in prompt


def test_agent_and_rag_are_not_the_same_bucket() -> None:
    jds, interviews = load_library_samples()
    agent_titles = [
        str(item.get("role") or "")
        for item in jds
        if assign_sample_role(item) == "agent"
    ]
    rag_titles = [
        str(item.get("role") or "")
        for item in jds
        if assign_sample_role(item) == "rag"
    ]
    assert any("Agent" in title or "agent" in title.lower() for title in agent_titles)
    assert any("搜索" in title or "RAG" in title.upper() or "应用" in title for title in rag_titles)
    assert not set(agent_titles) & set(rag_titles)
    assert len(interviews) > 0


def test_session_create_rejects_dropped_training_role() -> None:
    payload = {
        "github_url": "https://github.com/jingyaogong/minimind.git",
        "statement": "复现了 RoPE 与 RMSNorm。",
        "role": "training",
    }
    with pytest.raises(ValidationError):
        SessionCreate.model_validate(payload)
    SessionCreate.model_validate({**payload, "role": "llm-algo"})
    SessionCreate.model_validate({**payload, "role": "agent"})
    SessionCreate.model_validate({**payload, "role": "rag"})


def test_roles_api_matches_catalog() -> None:
    client = TestClient(app)
    payload = client.get("/api/roles").json()
    assert [item["id"] for item in payload["roles"]] == list(allowed_role_ids())


def test_interviewer_agent_api_returns_live_prompt_and_tools() -> None:
    client = TestClient(app)
    payload = client.get("/api/interviewer-agent", params={"role": "llm-algo"}).json()
    interviewer = payload["prompts"]["interviewer"]
    assert "话题锁（全文宪法）" in interviewer
    assert "具体岗位人设以本场注入的" in interviewer
    assert "话题锁（全文宪法）" in payload["system_prompt"]
    assert "LLM 算法实习 · 面试官人设" in payload["system_prompt"]
    assert payload["selected_role"] == "llm-algo"

    tool_names = [item["name"] for item in payload["tools"]]
    expected = [
        item["function"]["name"]  # type: ignore[index]
        for item in INTERVIEW_TURN_TOOLS
    ]
    assert tool_names == expected

    agent_page = client.get("/api/interviewer-agent", params={"role": "agent"}).json()
    assert agent_page["selected_role"] == "agent"
    assert "Agent 应用实习 · 面试官人设" in agent_page["system_prompt"]
    assert "LLM 算法实习 · 面试官人设" not in agent_page["prompts"]["role"]

    rejected = client.get("/api/interviewer-agent", params={"role": "training"})
    assert rejected.status_code == 400
