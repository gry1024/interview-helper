"""Pure helpers for the end report and the frozen review snapshot.

No LLM calls, no FastAPI routes, no writes to sessions/turns.
Replay must go through load_review_for_replay and must not call generators.
"""

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import re
from typing import Any

from app.review_models import ReviewSnapshot
from app.roles import role_label


APP_DIR = Path(__file__).resolve().parent
REPORT_PROMPT_PATH = APP_DIR / "prompts" / "report.md"
REVIEW_SNAPSHOT_SCHEMA_VERSION = 1
STATEMENT_PREVIEW_LIMIT = 40
REPORT_SECTION_TITLES = (
    "总评",
    "岗位匹配",
    "知识建议",
    "项目改良",
)
REPORT_SECTION_ALIASES = {
    "总评": ("总评", "综合评价", "整体评价"),
    "岗位匹配": (
        "岗位匹配",
        "岗位匹配对照",
        "岗位本质对照",
        "岗位本质",
        "本质对照",
    ),
    "知识建议": ("知识建议", "知识补习"),
    "项目改良": ("项目改良", "最小改造", "项目改造", "改造建议"),
}
LIVE_THOUGHT_FORBIDDEN = (
    "建议你",
    "总评",
    "复习",
    "岗位本质对照",
    "岗位匹配",
    "知识建议",
    "项目改良",
)
PRIMARY_BANDS = ("真懂", "懂但讲不出", "真不懂", "项目里没有")
HIGH_PRIMARY_BANDS = frozenset({"真懂", "懂但讲不出"})
LOW_PRIMARY_BANDS = frozenset({"真不懂", "项目里没有"})
PRIMARY_BAND_RE = re.compile(
    r"整场主档\s*[：:]\s*(真懂|懂但讲不出|真不懂|项目里没有)"
)
PRIMARY_BAND_RANK = {
    "真懂": 3,
    "懂但讲不出": 2,
    "真不懂": 1,
    "项目里没有": 1,
}


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


def extract_primary_band(report_text: str) -> str:
    """Read the single overall band required in the 总评 opening."""

    match = PRIMARY_BAND_RE.search(report_text or "")
    if not match:
        raise ValueError("报告总评必须标明整场主档")
    return match.group(1)


def _has_section_title(text: str, title: str) -> bool:
    blob = text or ""
    for alias in REPORT_SECTION_ALIASES.get(title, (title,)):
        if re.search(rf"^#{{1,6}}\s*{re.escape(alias)}\s*$", blob, re.M):
            return True
        if f"## {alias}" in blob:
            return True
    return False


HANGING_OPEN_QUOTE = re.compile(r"[「『“\"]+\s*$")
THIRD_BULLET_EMPTY = re.compile(r"岗位在意但本项目没有[：:]\s*$")
TRUNCATED_TAIL = re.compile(r"[：:、，,…]\s*$")
JOB_MATCH_HEADING = re.compile(
    r"^#{1,6}\s*(?:岗位匹配对照|岗位匹配|岗位本质对照|岗位本质|本质对照)\s*$",
    re.M,
)


def _close_job_match_body(section: str) -> str:
    raw = section or ""
    trimmed = raw.rstrip()
    if not (HANGING_OPEN_QUOTE.search(trimmed) or THIRD_BULLET_EMPTY.search(trimmed)):
        return raw
    body = HANGING_OPEN_QUOTE.sub("", trimmed).rstrip()
    if THIRD_BULLET_EMPTY.search(body):
        body += "本场未再展开到可核的岗位筛选项；不编造仓库没有的实现。"
    if "岗位在意但本项目没有" not in body:
        body += (
            "\n- 岗位在意但本项目没有：本场未再展开到可核的岗位筛选项；"
            "不编造仓库没有的实现。"
        )
    if TRUNCATED_TAIL.search(body):
        body += "不编造仓库没有的实现。"
    if raw.endswith("\n") and not body.endswith("\n"):
        body += "\n"
    return body


def salvage_truncated_report(text: str) -> str:
    """Close a truncated 岗位匹配 section so it does not end on an opening quote."""

    blob = text or ""
    heading = JOB_MATCH_HEADING.search(blob)
    if heading is None:
        return blob
    start = heading.end()
    following = re.search(r"^#{1,6}\s+\S+", blob[start:], re.M)
    if following:
        section = blob[start : start + following.start()]
        suffix = blob[start + following.start() :]
    else:
        section = blob[start:]
        suffix = ""
    return blob[:start] + _close_job_match_body(section) + suffix


def compose_report_text(model_output: str) -> str:
    """Accept a finished report. Keep every character; do not summarize."""

    if not isinstance(model_output, str) or not model_output:
        raise ValueError("报告不能为空")
    salvaged = salvage_truncated_report(model_output)
    missing = [
        title for title in REPORT_SECTION_TITLES if not _has_section_title(salvaged, title)
    ]
    if missing:
        raise ValueError(f"报告缺少必要段落: {'、'.join(missing)}")
    extract_primary_band(salvaged)
    return salvaged


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
        "岗位匹配": job_essence_compare,
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
    helps: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """User payload for the future end-report LLM call. No bodies omitted."""

    payload = {
        "role": session["role"],
        "role_label": role_label(str(session["role"])),
        "statement": session["statement"],
        "directions": _as_directions(session),
        "current_direction_id": session.get("current_direction_id"),
        "clone_ok": bool(session.get("clone_ok", False)),
        "help_count": len(helps or []),
        "helps": [
            {
                "question": item.get("question"),
                "hint": item.get("hint"),
                "looked_at_code": bool(item.get("looked_at_code")),
                "direction_id": item.get("direction_id"),
            }
            for item in (helps or [])
        ],
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
    helps: Sequence[Mapping[str, Any]] | None = None,
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
    help_copies = [
        {
            "id": item.get("id"),
            "session_id": item.get("session_id", session["id"]),
            "created_at": item.get("created_at"),
            "question": item.get("question") or "",
            "hint": item.get("hint") or "",
            "looked_at_code": bool(item.get("looked_at_code")),
            "inspect_public": item.get("inspect_public"),
            "direction_id": item.get("direction_id"),
        }
        for item in (helps or [])
    ]
    return ReviewSnapshot.model_validate(
        {
            "schema_version": REVIEW_SNAPSHOT_SCHEMA_VERSION,
            "session": session_copy,
            "turns": turn_copies,
            "report": {"text": frozen_report},
            "helps": help_copies,
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
    helps: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Serialize the end-moment snapshot. Only call from the future /end handler."""

    return snapshot_to_json(
        assemble_review_snapshot(session, turns, report_text, helps)
    )


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
