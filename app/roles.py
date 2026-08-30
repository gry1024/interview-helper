"""Single source of truth for supported interview roles.

Catalog: `app/jd/roles.json`. Each sample in the JD/面经 library is assigned
exactly one primary role so interviewer personas stay distinct. Stats are
computed live from the library files, not frozen in the catalog.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Iterable


APP_DIR = Path(__file__).resolve().parent
JD_DIR = APP_DIR / "jd"
PROMPTS_DIR = APP_DIR / "prompts"
ROLES_PATH = JD_DIR / "roles.json"
ROLE_PROMPT_DIR = PROMPTS_DIR / "roles"

_SEARCH_IN_TITLE = re.compile(r"搜索|search|\brag\b|检索", re.I)
_NUMBERED_ITEM = re.compile(
    r"(?:^|[\n；;])\s*(?:\d+[\.、．\)]\s*|Q\d+[:：]\s*|问[:：]\s*)(.+?)"
    r"(?=(?:[\n；;]\s*(?:\d+[\.、．\)]|Q\d+|问[:：])|$))",
    re.S,
)
_QUESTION_SENTENCE = re.compile(r"[^。！？\n]{8,80}[？?]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_role_catalog() -> dict[str, Any]:
    raw = _read_json(ROLES_PATH)
    roles = raw.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError("roles.json 缺少 roles")
    ids = [str(item.get("id") or "").strip() for item in roles]
    if len(ids) != len(set(ids)) or not all(ids):
        raise ValueError("roles.json 岗位 id 不合法")
    return raw


def list_roles() -> list[dict[str, Any]]:
    return list(load_role_catalog()["roles"])


def allowed_role_ids() -> tuple[str, ...]:
    return tuple(str(item["id"]) for item in list_roles())


def is_allowed_role(role: str) -> bool:
    return role in allowed_role_ids()


def role_label(role: str) -> str:
    for item in list_roles():
        if item["id"] == role:
            return str(item.get("label") or role)
    return role


def role_one_liner(role: str) -> str:
    for item in list_roles():
        if item["id"] == role:
            return str(item.get("one_liner") or "")
    return ""


def role_entry(role: str) -> dict[str, Any]:
    for item in list_roles():
        if item["id"] == role:
            return dict(item)
    raise KeyError(role)


def _sample_blob(sample: dict[str, Any]) -> str:
    return " ".join(
        str(sample.get(key) or "")
        for key in ("role", "text", "requirements")
    )


def _hit_count(text: str, terms: Iterable[str]) -> int:
    lowered = text.lower()
    total = 0
    for term in terms:
        needle = str(term).lower()
        if not needle:
            continue
        total += lowered.count(needle)
    return total


def assign_sample_role(sample: dict[str, Any]) -> str:
    """Exclusive primary role for one JD or interview sample."""

    title = str(sample.get("role") or "")
    blob = _sample_blob(sample)
    agent = role_entry("agent")
    rag = role_entry("rag")

    title_agent = _hit_count(title, agent["title_terms"])
    title_rag = _hit_count(title, rag["title_terms"])
    if title_agent and _SEARCH_IN_TITLE.search(title):
        return "rag"
    if title_agent:
        return "agent"
    if title_rag:
        return "rag"

    body_rag = _hit_count(blob, rag["body_terms"])
    body_agent = _hit_count(blob, agent["body_terms"])
    if body_rag >= 2 and body_rag >= body_agent:
        return "rag"
    if body_agent >= 3 and body_agent > body_rag:
        return "agent"
    return "llm-algo"


@lru_cache(maxsize=1)
def load_library_samples() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jds = list(_read_json(JD_DIR / "jds.json"))
    interviews = list(_read_json(JD_DIR / "interviews.json"))
    return jds, interviews


def samples_for_role(
    role: str,
    *,
    jds: list[dict[str, Any]] | None = None,
    interviews: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if jds is None or interviews is None:
        jds, interviews = load_library_samples()
    role_jds = [item for item in jds if assign_sample_role(item) == role]
    role_ivs = [item for item in interviews if assign_sample_role(item) == role]
    return role_jds, role_ivs


def role_corpus_stats(role: str) -> dict[str, Any]:
    jds, interviews = samples_for_role(role)
    return {
        "id": role,
        "label": role_label(role),
        "one_liner": role_one_liner(role),
        "jd_count": len(jds),
        "interview_count": len(interviews),
        "sample_ids": [
            str(item.get("id") or "")
            for item in jds + interviews
            if item.get("id")
        ],
    }


@lru_cache(maxsize=1)
def all_role_stats() -> list[dict[str, Any]]:
    jds, interviews = load_library_samples()
    stats: list[dict[str, Any]] = []
    for role_id in allowed_role_ids():
        role_jds, role_ivs = samples_for_role(role_id, jds=jds, interviews=interviews)
        stats.append(
            {
                "id": role_id,
                "label": role_label(role_id),
                "one_liner": role_one_liner(role_id),
                "jd_count": len(role_jds),
                "interview_count": len(role_ivs),
                "sample_ids": [
                    str(item.get("id") or "")
                    for item in role_jds + role_ivs
                    if item.get("id")
                ],
            }
        )
    return stats


def role_prompt_path(role: str) -> Path:
    return ROLE_PROMPT_DIR / f"{role}.md"


def load_role_prompt(role: str) -> str:
    path = role_prompt_path(role)
    if not path.is_file():
        raise FileNotFoundError(f"缺少岗位人设文件：{path}")
    return path.read_text(encoding="utf-8")


def load_interviewer_prompt() -> str:
    return (PROMPTS_DIR / "interviewer.md").read_text(encoding="utf-8")


def load_code_exercise_prompt() -> str:
    return (PROMPTS_DIR / "code_exercise.md").read_text(encoding="utf-8")


def load_teacher_prompt() -> str:
    return (PROMPTS_DIR / "teacher.md").read_text(encoding="utf-8")


def load_report_prompt_text() -> str:
    return (PROMPTS_DIR / "report.md").read_text(encoding="utf-8")


def extract_questions(text: str, *, limit: int = 40) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _NUMBERED_ITEM.finditer(text or ""):
        snippet = _CONTROL.sub("", match.group(1)).strip()
        snippet = re.sub(r"\s+", " ", snippet)
        if 6 <= len(snippet) <= 120 and snippet not in seen:
            seen.add(snippet)
            found.append(snippet)
            if len(found) >= limit:
                return found
    for match in _QUESTION_SENTENCE.finditer(text or ""):
        snippet = _CONTROL.sub("", match.group(0)).strip()
        if snippet not in seen and 8 <= len(snippet) <= 80:
            seen.add(snippet)
            found.append(snippet)
            if len(found) >= limit:
                break
    return found


_SUMMARY_KEYWORDS = (
    "transformer",
    "attention",
    "rope",
    "rmsnorm",
    "swiglu",
    "mha",
    "gqa",
    "kv cache",
    "sft",
    "dpo",
    "ppo",
    "grpo",
    "rlhf",
    "lora",
    "预训练",
    "后训练",
    "对齐",
    "rag",
    "chunk",
    "embedding",
    "rerank",
    "召回",
    "agent",
    "工具调用",
    "planner",
    "memory",
    "mcp",
    "fallback",
    "显存",
    "量化",
    "分布式",
)


def extract_role_summary(role: str) -> dict[str, Any]:
    """Walk every sample assigned to this role and build a structured digest."""

    jds, interviews = samples_for_role(role)
    samples = jds + interviews
    keyword_counts: dict[str, int] = {key: 0 for key in _SUMMARY_KEYWORDS}
    companies: dict[str, int] = {}
    questions: list[str] = []
    jd_excerpts: list[str] = []
    for sample in samples:
        blob = _sample_blob(sample)
        lowered = blob.lower()
        for key in _SUMMARY_KEYWORDS:
            keyword_counts[key] += lowered.count(key.lower())
        company = str(sample.get("company") or "").strip()
        if company:
            companies[company] = companies.get(company, 0) + 1
        questions.extend(extract_questions(str(sample.get("text") or ""), limit=8))
    seen_q: set[str] = set()
    unique_questions: list[str] = []
    for item in questions:
        if item in seen_q:
            continue
        seen_q.add(item)
        unique_questions.append(item)
        if len(unique_questions) >= 48:
            break
    for sample in jds:
        excerpt = re.sub(r"\s+", " ", str(sample.get("text") or "")).strip()
        if excerpt:
            jd_excerpts.append(
                f"{sample.get('company')} / {sample.get('role')}: {excerpt[:220]}"
            )
    hot = [
        {"term": term, "count": count}
        for term, count in sorted(keyword_counts.items(), key=lambda item: -item[1])
        if count > 0
    ]
    return {
        "role": role,
        "label": role_label(role),
        "jd_count": len(jds),
        "interview_count": len(interviews),
        "sample_ids": [str(item.get("id") or "") for item in samples if item.get("id")],
        "companies": sorted(companies.items(), key=lambda item: -item[1])[:16],
        "hot_terms": hot[:24],
        "questions": unique_questions,
        "jd_excerpts": jd_excerpts[:18],
        "covered_all": len(samples) == len(jds) + len(interviews)
        and len(samples) == (len(jds) + len(interviews)),
    }
