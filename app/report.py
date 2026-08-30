"""Pure helpers for the end report and the frozen review snapshot.

No LLM calls, no FastAPI routes, no writes to sessions/turns.
Replay must go through load_review_for_replay and must not call generators.
"""

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from app.review_models import ReviewSnapshot


APP_DIR = Path(__file__).resolve().parent
REPORT_PROMPT_PATH = APP_DIR / "prompts" / "report.md"
REVIEW_SNAPSHOT_SCHEMA_VERSION = 1
STATEMENT_PREVIEW_LIMIT = 40
ROLE_LABELS = {
    "llm-algo": "LLM 算法实习",
    "training": "大模型训练与对齐",
    "rag": "RAG 与 Agent 应用",
}
REPORT_SECTION_TITLES = (
    "总评",
    "岗位本质对照",
    "知识建议",
    "项目改良",
)
LIVE_THOUGHT_FORBIDDEN = (
    "建议你",
    "总评",
    "复习",
    "岗位本质对照",
    "知识建议",
    "项目改良",
)


def load_report_prompt() -> str:
    return REPORT_PROMPT_PATH.read_text(encoding="utf-8")


def statement_preview(statement: str, limit: int = STATEMENT_PREVIEW_LIMIT) -> str:
    """List-card preview: first N characters. Full statement stays in the snapshot."""

    return statement[:limit]


def thoughts_leak_report_content(turns: Sequence[Mapping[str, Any]]) -> bool:
    """True if any live thought already contains end-report prescriptions."""

    for turn in turns:
        if turn.get("role") != "thought":
            continue
        body = turn.get("body") or ""
        if any(marker in body for marker in LIVE_THOUGHT_FORBIDDEN):
            return True
    return False


def compose_report_text(model_output: str) -> str:
    """Accept a finished report. Keep every character; do not summarize."""

    if not isinstance(model_output, str) or not model_output:
        raise ValueError("报告不能为空")
    missing = [title for title in REPORT_SECTION_TITLES if title not in model_output]
    if missing:
        raise ValueError(f"报告缺少必要段落: {'、'.join(missing)}")
    return model_output


def build_report_from_parts(
    *,
    overall: str,
    job_essence_compare: str,
    knowledge_advice: str,
    project_improve: str,
) -> str:
    """Assemble the four required sections without omitting any part body."""

    parts = {
        "总评": overall,
        "岗位本质对照": job_essence_compare,
        "知识建议": knowledge_advice,
        "项目改良": project_improve,
    }
    for title, body in parts.items():
        if not isinstance(body, str) or not body:
            raise ValueError(f"报告段落「{title}」不能为空")
    return "\n\n".join(
        f"## {title}\n\n{parts[title]}" for title in REPORT_SECTION_TITLES
    )


def build_end_report_context(
    session: Mapping[str, Any],
    turns: Sequence[Mapping[str, Any]],
) -> str:
    """User payload for the future end-report LLM call. No bodies omitted."""

    payload = {
        "role": session["role"],
        "role_label": ROLE_LABELS.get(str(session["role"]), session["role"]),
        "statement": session["statement"],
        "directions": _as_directions(session),
        "current_direction_id": session.get("current_direction_id"),
        "clone_ok": bool(session.get("clone_ok", False)),
        "turns": [
            {
                "seq": turn["seq"],
                "role": turn["role"],
                "body": turn["body"],
                "direction_id": turn.get("direction_id"),
                "meta": _as_meta(turn),
            }
            for turn in turns
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def assemble_review_snapshot(
    session: Mapping[str, Any],
    turns: Sequence[Mapping[str, Any]],
    report_text: str,
) -> ReviewSnapshot:
    """Freeze session + all turns + full report at the end moment.

    Does not mutate the input mappings. Snapshot session.status is always ended.
    """

    frozen_report = compose_report_text(report_text)
    session_copy = {
        "id": session["id"],
        "created_at": session["created_at"],
        "github_url": session["github_url"],
        "statement": session["statement"],
        "role": session["role"],
        "directions": _as_directions(session),
        "current_direction_id": session["current_direction_id"],
        "clone_path": session.get("clone_path"),
        "clone_ok": bool(session.get("clone_ok", False)),
        "status": "ended",
        "first_question": session["first_question"],
    }
    turn_copies = [
        {
            "id": turn.get("id"),
            "session_id": turn.get("session_id", session["id"]),
            "seq": turn["seq"],
            "role": turn["role"],
            "body": turn["body"],
            "direction_id": turn.get("direction_id"),
            "meta": _as_meta(turn),
        }
        for turn in turns
    ]
    return ReviewSnapshot.model_validate(
        {
            "schema_version": REVIEW_SNAPSHOT_SCHEMA_VERSION,
            "session": session_copy,
            "turns": turn_copies,
            "report": {"text": frozen_report},
        }
    )


def snapshot_to_json(snapshot: ReviewSnapshot) -> str:
    return json.dumps(
        snapshot.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def dump_end_snapshot(
    session: Mapping[str, Any],
    turns: Sequence[Mapping[str, Any]],
    report_text: str,
) -> str:
    """Serialize the end-moment snapshot. Only call from the future /end handler."""

    return snapshot_to_json(assemble_review_snapshot(session, turns, report_text))


def load_review_for_replay(snapshot_json: str) -> ReviewSnapshot:
    """Read-only replay entry. Parse stored JSON only; never generate or rewrite."""

    if not snapshot_json:
        raise ValueError("snapshot_json 不能为空")
    return ReviewSnapshot.model_validate_json(snapshot_json)


def _as_directions(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    if "directions" in session and session["directions"] is not None:
        directions = session["directions"]
        if isinstance(directions, str):
            directions = json.loads(directions)
        return [dict(item) for item in directions]
    if session.get("directions_json"):
        return list(json.loads(session["directions_json"]))
    raise ValueError("session 缺少 directions")


def _as_meta(turn: Mapping[str, Any]) -> Any:
    if "meta" in turn:
        meta = turn["meta"]
        if isinstance(meta, str) and meta:
            return json.loads(meta)
        return meta
    raw = turn.get("meta_json")
    if isinstance(raw, str) and raw:
        return json.loads(raw)
    return raw
