"""Catalog-backed hand-write exercises; the model must not invent prompts."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Mapping


JD_DIR = Path(__file__).resolve().parent.parent / "jd"
BANK_PATH = JD_DIR / "code_exercises.json"
EXERCISE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ERROR_UNKNOWN_ID = "题库无此 id，不要现场编题。"
ERROR_NO_TOPIC_MATCH = "题库没有与该 topic 对应的题，不要现场编题。"
ERROR_MISSING_SELECTOR = "必须提供 exercise_id 或 topic，不要现场编题。"
ERROR_DUPLICATE = "本场已出过此题，不要重复打开。"
ERROR_ONE_PER_TURN = "本轮已打开一题，不要再调用。"
ERROR_BAD_ID = "exercise_id 不合法。"


CODE_EXERCISE_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "code_exercise",
        "description": (
            "从已搜集面经题库打开一道 Python 手撕题（注意力、RoPE、RMSNorm、"
            "SwiGLU、KV Cache、LoRA、tokenizer 等）。用于核实会不会写。"
            "必须带 exercise_id 或 topic；禁止自拟题面或出无关算法题。"
            "同一场同一题不重复，一轮最多一题。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exercise_id": {
                    "type": "string",
                    "description": "题库 id，优先使用，例如 mha-forward、rope-apply",
                },
                "topic": {
                    "type": "string",
                    "description": "主题关键词，例如 Multi-Head Attention、RoPE、KV cache",
                },
            },
        },
    },
}


@dataclass(frozen=True)
class CodeExercise:
    id: str
    title: str
    prompt: str
    language: str
    starter: str
    source_ids: tuple[str, ...]
    topics: tuple[str, ...]
    roles: tuple[str, ...]

    def sse_payload(self) -> dict[str, str]:
        return {
            "exercise_id": self.id,
            "title": self.title,
            "prompt": self.prompt,
            "language": self.language,
            "starter": self.starter,
        }


@dataclass(frozen=True)
class CodeExerciseOpen:
    ok: bool
    error: str | None
    exercise: CodeExercise | None

    def for_model(self) -> str:
        if not self.ok or self.exercise is None:
            return (
                f"ok=false\nerror={self.error or ERROR_NO_TOPIC_MATCH}\n"
                "不要现场编题，只能从题库选题；匹配失败就继续口头追问。"
            )
        exercise = self.exercise
        return (
            f"ok=true\nexercise_id={exercise.id}\ntitle={exercise.title}\n"
            f"source_ids={','.join(exercise.source_ids)}\n"
            "已向学生打开编辑器。下一问承接这道手撕，不要重复打开，"
            "不要念题库以外的题目，不要假装编译运行。"
        )

    def for_public(self) -> str:
        if not self.ok or self.exercise is None:
            return "本题无法打开，请继续口头回答。"
        return f"已打开《{self.exercise.title}》"

    def sse_payload(self) -> dict[str, str] | None:
        if not self.ok or self.exercise is None:
            return None
        return self.exercise.sse_payload()


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _parse_exercise(raw: Mapping[str, Any]) -> CodeExercise | None:
    exercise_id = str(raw.get("id") or "").strip()
    title = str(raw.get("title") or "").strip()
    prompt = str(raw.get("prompt") or "").strip()
    starter = raw.get("starter")
    source_ids = _as_str_tuple(raw.get("source_ids"))
    topics = _as_str_tuple(raw.get("topics"))
    if not EXERCISE_ID_RE.fullmatch(exercise_id):
        return None
    if not title or not prompt or not isinstance(starter, str) or not starter:
        return None
    if not source_ids or not topics:
        return None
    language = str(raw.get("language") or "python").strip() or "python"
    from app.roles import allowed_role_ids

    allowed = set(allowed_role_ids())
    roles = tuple(
        item for item in _as_str_tuple(raw.get("roles")) if item in allowed
    ) or tuple(allowed_role_ids())
    return CodeExercise(
        id=exercise_id,
        title=title,
        prompt=prompt,
        language=language,
        starter=starter,
        source_ids=source_ids,
        topics=topics,
        roles=roles,
    )


@lru_cache(maxsize=1)
def load_exercises() -> tuple[CodeExercise, ...]:
    """Load the sourced bank; skip malformed rows instead of inventing titles."""

    raw = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return ()
    seen: set[str] = set()
    loaded: list[CodeExercise] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        exercise = _parse_exercise(item)
        if exercise is None or exercise.id in seen:
            continue
        seen.add(exercise.id)
        loaded.append(exercise)
    return tuple(loaded)


def get_exercise(exercise_id: str) -> CodeExercise | None:
    cleaned = (exercise_id or "").strip()
    for exercise in load_exercises():
        if exercise.id == cleaned:
            return exercise
    return None


def catalog_for_prompt() -> str:
    lines = ["可调用手撕题库（只能从下列选题，禁止编题）："]
    for exercise in load_exercises():
        topics = "、".join(exercise.topics)
        lines.append(f"- {exercise.id}：{exercise.title}（{topics}）")
    return "\n".join(lines)


def used_exercise_ids(turns: list[dict[str, Any]] | None) -> set[str]:
    used: set[str] = set()
    for turn in turns or []:
        meta = turn.get("meta")
        if isinstance(meta, dict):
            _collect_used_id(used, meta)
            continue
        if isinstance(meta, list):
            for item in meta:
                if isinstance(item, dict):
                    _collect_used_id(used, item)
    return used


def _collect_used_id(used: set[str], item: Mapping[str, Any]) -> None:
    if item.get("kind") == "code_submission" and item.get("exercise_id"):
        used.add(str(item["exercise_id"]))
    if item.get("name") == "code_exercise":
        args = item.get("args") if isinstance(item.get("args"), Mapping) else {}
        candidate = item.get("exercise_id") or args.get("exercise_id")
        if candidate:
            used.add(str(candidate))


def _normalize(text: str) -> str:
    lowered = text.casefold()
    return re.sub(r"[\s_\-/]+", " ", lowered).strip()


def match_exercise(
    topic: str,
    *,
    used_ids: set[str] | None = None,
    role: str = "",
    direction_text: str = "",
) -> CodeExercise | None:
    needle = _normalize(topic)
    if not needle:
        return None
    used = used_ids or set()
    scored: list[tuple[int, CodeExercise]] = []
    direction_blob = _normalize(direction_text)
    for exercise in load_exercises():
        if exercise.id in used:
            continue
        hay = _normalize(
            " ".join((exercise.id, exercise.title, " ".join(exercise.topics)))
        )
        score = 0
        if needle == exercise.id or needle == _normalize(exercise.title):
            score += 8
        if needle in hay or hay in needle:
            score += 4
        for keyword in exercise.topics:
            token = _normalize(keyword)
            if token and (token in needle or needle in token):
                score += 3
        if role and role in exercise.roles:
            score += 1
        if direction_blob:
            score += sum(
                1
                for keyword in exercise.topics
                if _normalize(keyword) and _normalize(keyword) in direction_blob
            )
        if score:
            scored.append((score, exercise))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return scored[0][1]


def resolve_exercise(
    arguments: Mapping[str, Any] | None,
    *,
    used_ids: set[str] | None = None,
    role: str = "",
    direction_text: str = "",
    already_opened_this_turn: bool = False,
) -> CodeExerciseOpen:
    if already_opened_this_turn:
        return CodeExerciseOpen(ok=False, error=ERROR_ONE_PER_TURN, exercise=None)

    payload = arguments if isinstance(arguments, Mapping) else {}
    raw_id = payload.get("exercise_id")
    raw_topic = payload.get("topic")
    exercise_id = raw_id.strip() if isinstance(raw_id, str) else ""
    topic = raw_topic.strip() if isinstance(raw_topic, str) else ""
    used = used_ids or set()

    if exercise_id:
        if not EXERCISE_ID_RE.fullmatch(exercise_id):
            return CodeExerciseOpen(ok=False, error=ERROR_BAD_ID, exercise=None)
        exercise = get_exercise(exercise_id)
        if exercise is None:
            return CodeExerciseOpen(ok=False, error=ERROR_UNKNOWN_ID, exercise=None)
        if exercise.id in used:
            return CodeExerciseOpen(ok=False, error=ERROR_DUPLICATE, exercise=None)
        return CodeExerciseOpen(ok=True, error=None, exercise=exercise)

    if not topic:
        topic = direction_text.strip()
    if not topic:
        return CodeExerciseOpen(ok=False, error=ERROR_MISSING_SELECTOR, exercise=None)

    exercise = match_exercise(
        topic,
        used_ids=used,
        role=role,
        direction_text=direction_text,
    )
    if exercise is None:
        return CodeExerciseOpen(ok=False, error=ERROR_NO_TOPIC_MATCH, exercise=None)
    return CodeExerciseOpen(ok=True, error=None, exercise=exercise)


def run_code_exercise_from_tool_args(
    arguments: Mapping[str, Any] | None,
    *,
    used_ids: set[str] | None = None,
    role: str = "",
    direction_text: str = "",
    already_opened_this_turn: bool = False,
) -> CodeExerciseOpen:
    """Bind a model tool-call payload to a catalog exercise."""

    return resolve_exercise(
        arguments,
        used_ids=used_ids,
        role=role,
        direction_text=direction_text,
        already_opened_this_turn=already_opened_this_turn,
    )


def format_submission_answer(exercise: CodeExercise, code: str) -> str:
    return (
        f"[手撕提交 exercise_id={exercise.id}]\n"
        f"题目：{exercise.title}\n"
        f"题面：{exercise.prompt}\n"
        f"学生代码：\n{code}"
    )
