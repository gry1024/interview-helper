"""Hand-write exercises sourced from the bank index or interview originals."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


JD_DIR = Path(__file__).resolve().parent.parent / "jd"
BANK_PATH = JD_DIR / "code_exercises.json"
EXERCISE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ERROR_UNKNOWN_ID = "题库无此 id，不要现场编题。"
ERROR_NO_TOPIC_MATCH = "面经没有提到相关手撕，不要现场编题。"
ERROR_UNRELATED_ALGO = "禁止出链表、排序、背包等无关算法题。"
ERROR_MISSING_SELECTOR = "必须提供 exercise_id 或 topic，不要现场编题。"
ERROR_DUPLICATE = "本场已出过此题，不要重复打开。"
ERROR_ONE_PER_TURN = "本轮已打开一题，不要再调用。"
ERROR_BAD_ID = "exercise_id 不合法。"


CODE_EXERCISE_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "code_exercise",
        "description": (
            "聊到面经里提到的具体实现（RoPE、MHA、RMSNorm、KV Cache、LoRA 等）"
            "时必须打开手撕，不要只口头连问细节。"
            "必须带 exercise_id 或 topic。先查加速题库，没有命中再按面经原问出题。"
            "禁止自拟新考点或出链表/排序/背包。没有相关面经就继续口头问。"
            "同一场同一题不重复，一轮最多一题。题已打开或已交过就不要再调。"
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
        payload = {
            "exercise_id": self.id,
            "title": self.title,
            "prompt": self.prompt,
            "language": self.language,
            "starter": self.starter,
        }
        if self.source_ids:
            payload["sample_id"] = self.source_ids[0]
        return payload


@dataclass(frozen=True)
class CodeExerciseOpen:
    ok: bool
    error: str | None
    exercise: CodeExercise | None

    def for_model(self) -> str:
        if not self.ok or self.exercise is None:
            return (
                f"ok=false\nerror={self.error or ERROR_NO_TOPIC_MATCH}\n"
                "不要现场编题。题已打开或匹配失败就继续口头追问，"
                "必须输出带 next_question 的 JSON，不要只写 thought。"
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


_DYNAMIC_EXERCISES: dict[str, CodeExercise] = {}
GENERIC_STARTER = (
    "def forward(*args, **kwargs):\n"
    "    # 按面经原问补全当前这一步，不要改成无关算法题\n"
    "    raise NotImplementedError\n"
)
UNRELATED_ALGO_RE = re.compile(
    r"链表|背包|两数之和|三数之和|快排|快速排序|归并排序|堆排序|"
    r"滑动窗口|二叉树|最近公共祖先|合并区间|最长有效括号|"
    r"划分子集|井字棋|路径总和|最小.?k.?个|覆盖字串|麻将|"
    r"two.?sum|leetcode|乘积最大|反转链表|最长子数组",
    re.I,
)


def get_exercise(exercise_id: str) -> CodeExercise | None:
    cleaned = (exercise_id or "").strip()
    for exercise in load_exercises():
        if exercise.id == cleaned:
            return exercise
    return _DYNAMIC_EXERCISES.get(cleaned)


def _remember_exercise(exercise: CodeExercise) -> CodeExercise:
    _DYNAMIC_EXERCISES[exercise.id] = exercise
    return exercise


def catalog_for_prompt() -> str:
    lines = ["可调用手撕（题库作索引；面经里提到的相关手撕才出，禁止编题）："]
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
        payload = item.get("payload") if isinstance(item.get("payload"), Mapping) else {}
        candidate = (
            item.get("exercise_id")
            or args.get("exercise_id")
            or payload.get("exercise_id")
        )
        if candidate:
            used.add(str(candidate))


def _normalize(text: str) -> str:
    lowered = text.casefold()
    return re.sub(r"[\s_\-/]+", " ", lowered).strip()


STRONG_TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "rope-apply": ("rope", "rotary", "旋转位置编码"),
    "rmsnorm-forward": ("rmsnorm", "rms norm"),
    "swiglu-ffn": ("swiglu",),
    "kv-cache-step": ("kv cache", "kv-cache"),
    "lora-linear": ("lora", "qlora"),
    "mha-forward": ("multi-head", "multihead", "mha", "多头注意力"),
    "scaled-dot-product": ("scaled dot", "scaled attention"),
    "causal-mask": ("causal mask", "因果 mask", "因果mask"),
    "tokenizer-bpe-merge": ("bpe", "tokenizer"),
    "mqa-forward": ("mqa", "multi-query", "multi query"),
    "gqa-repeat-kv": ("gqa", "grouped query"),
    "paged-kv-lookup": ("pagedattention", "paged attention", "block table"),
    "softmax-stable": ("数值稳定 softmax", "stable softmax"),
}
IMPLEMENTATION_DEPTH = re.compile(
    r"实现|手写|怎么写|怎么算|前向|公式|旋转|旋的是|加在哪|"
    r"apply_?rope|偶数维|两两|分组|"
    r"q\s*/\s*k|q 和 k|qkv|d_head|sqrt|缩放|"
    r"mask|cache|低秩|alpha|下三角|block.?table|补全",
    re.I,
)


def match_implementation_exercise(
    *,
    recent_text: str,
    current_text: str,
    used_ids: set[str] | None = None,
) -> CodeExercise | None:
    """Pick a bank exercise once talk has reached a sourced implementation."""

    if not IMPLEMENTATION_DEPTH.search(current_text or ""):
        return None
    blob = _normalize(f"{recent_text}\n{current_text}")
    used = used_ids or set()
    hits: list[tuple[int, CodeExercise]] = []
    for exercise in load_exercises():
        if exercise.id in used:
            continue
        score = 0
        for alias in STRONG_TOPIC_ALIASES.get(exercise.id, ()):
            token = _normalize(alias)
            if token and token in blob:
                score += 10 + len(token)
        if score:
            hits.append((score, exercise))
    if hits:
        hits.sort(key=lambda item: (-item[0], item[1].id))
        return hits[0][1]
    query = (recent_text or current_text or "")[:120]
    if is_unrelated_algorithm(query):
        return None
    return match_interview_exercise(query, used_ids=used)


def is_unrelated_algorithm(text: str) -> bool:
    return bool(UNRELATED_ALGO_RE.search(text or ""))


def _topic_in_text(topic: str, text: str) -> bool:
    needle = _normalize(topic)
    hay = _normalize(text)
    if needle and needle in hay:
        return True
    tokens = [token for token in re.split(r"[\s_\-/]+", needle) if len(token) >= 2]
    tokens.extend(_normalize(chunk) for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", topic or ""))
    return any(token and token in hay for token in tokens)


def _interview_exercise_id(sample_id: str, snippet: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (sample_id or "sample").lower()).strip("-")
    slug = (slug or "sample")[:48]
    digest = hashlib.sha1((snippet or "").encode("utf-8")).hexdigest()[:8]
    return f"iv-{slug}-{digest}"


def _starter_for_interview(topic: str, snippet: str) -> str:
    bank = match_exercise(snippet) or match_exercise(topic)
    if bank is not None:
        return bank.starter
    return GENERIC_STARTER


def _exercise_from_interview_hit(hit: Any, topic: str) -> CodeExercise:
    snippet = re.sub(r"\s+", " ", str(getattr(hit, "snippet", "") or "")).strip()
    title_seed = snippet[:24].rstrip("，,。；; ") or topic[:20] or "手撕"
    prompt = (
        "对照面经原问，用 Python 写出当前这一步。不要改成链表、排序、背包。"
        f"\n\n原问：{snippet}"
    )
    sample = str(getattr(hit, "sample_id", "")).strip()
    exercise = CodeExercise(
        id=_interview_exercise_id(sample, snippet),
        title=f"手撕 {title_seed}",
        prompt=prompt,
        language="python",
        starter=_starter_for_interview(topic, snippet),
        source_ids=(sample,) if sample else ("interview",),
        topics=_as_str_tuple(topic),
        roles=(),
    )
    return _remember_exercise(exercise)


def match_interview_exercise(
    topic: str,
    *,
    used_ids: set[str] | None = None,
) -> CodeExercise | None:
    """Open a 手撕 from interview originals when the json bank has no hit."""

    cleaned = (topic or "").strip()
    if not cleaned or is_unrelated_algorithm(cleaned):
        return None
    from app.tools.search_library import search_handwrite_interviews

    used = used_ids or set()
    result = search_handwrite_interviews(cleaned)
    for hit in result.hits:
        snippet = hit.snippet or ""
        if not _topic_in_text(cleaned, snippet):
            continue
        if is_unrelated_algorithm(snippet) and is_unrelated_algorithm(cleaned):
            continue
        exercise_id = _interview_exercise_id(hit.sample_id, snippet)
        if exercise_id in used:
            continue
        return _exercise_from_interview_hit(hit, cleaned)
    return None


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
    if exercise is None and is_unrelated_algorithm(topic):
        return CodeExerciseOpen(ok=False, error=ERROR_UNRELATED_ALGO, exercise=None)
    if exercise is None:
        exercise = match_interview_exercise(topic, used_ids=used)
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
    """Bind a model tool-call payload to a bank or interview-sourced exercise."""

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


def exercise_from_opened_turns(
    turns: list[dict[str, Any]] | None,
    exercise_id: str,
) -> CodeExercise | None:
    """Recover an opened exercise (bank or 面经) from turn meta payloads."""

    wanted = (exercise_id or "").strip()
    if not wanted:
        return None
    found = get_exercise(wanted)
    if found is not None:
        return found
    for turn in turns or []:
        meta = turn.get("meta")
        if isinstance(meta, dict):
            items = [meta]
        elif isinstance(meta, list):
            items = meta
        else:
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            payload = item.get("payload")
            if not isinstance(payload, Mapping):
                continue
            if str(payload.get("exercise_id") or "") != wanted:
                continue
            starter = payload.get("starter")
            prompt = str(payload.get("prompt") or "").strip()
            title = str(payload.get("title") or "").strip() or "手撕代码"
            if not isinstance(starter, str) or not starter or not prompt:
                continue
            sample = str(payload.get("sample_id") or "").strip()
            return _remember_exercise(
                CodeExercise(
                    id=wanted,
                    title=title,
                    prompt=prompt,
                    language=str(payload.get("language") or "python").strip() or "python",
                    starter=starter,
                    source_ids=(sample,) if sample else ("interview",),
                    topics=(),
                    roles=(),
                )
            )
    return None
