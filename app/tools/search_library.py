"""Lexical search over collected JD/interview samples.

The corpus is hundreds of Chinese notes, not millions of tokens. A local
BM25-style index over original snippets beats an embedding RAG here: no extra
API, no invented paraphrase, and numbered 面经 questions stay intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import log
import json
from pathlib import Path
import re
from typing import Any, Mapping


JD_DIR = Path(__file__).resolve().parent.parent / "jd"
MAX_HITS = 10
MIN_HIT_SCORE = 8.0
SNIPPET_CHARS = 220
ERROR_EMPTY_QUERY = "检索词为空。"
PROCESS_QUERY = re.compile(
    r"(请)?(继续问|继续吧|往下问|下一问|换个?(话题|方向|问题)|换话题|好的|嗯嗯?|然后呢)"
)

LATIN_TOKEN = re.compile(r"[a-z0-9#+]+", re.I)
CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
NUMBERED_ITEM = re.compile(
    r"(?:^|[\n；;])\s*(?:\d+[\.、．\)]\s*|Q\d+[:：]\s*|问[:：]\s*)(.+?)(?=(?:[\n；;]\s*(?:\d+[\.、．\)]|Q\d+|问[:：])|$))",
    re.S,
)
QUESTION_SENTENCE = re.compile(r"[^。！？\n]{6,80}[？?]")


SEARCH_LIBRARY_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "search_library",
        "description": (
            "按当前话题检索 JD/面经库，用相关原问改写下一问。"
            "query 必须是当前技术话题（RoPE、LoRA 秩、KV cache），"
            "不要用「请继续问吧 / 换个话题 / 好的」当检索词。"
            "相关就返回，条数不固定；没有相关原问就空着，不要凑条数。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "当前要问的点，例如 Decoder 因果注意力 QKV、LoRA 秩、scaled attention",
                },
                "kind": {
                    "type": "string",
                    "enum": ["interview", "jd", "any"],
                    "description": "默认 interview；对岗位要求可查 jd",
                },
            },
            "required": ["query"],
        },
    },
}


@dataclass(frozen=True)
class LibraryChunk:
    sample_id: str
    kind: str
    company: str
    role: str
    source_name: str
    source_url: str
    snippet: str
    tokens: tuple[str, ...]


@dataclass
class LibraryHit:
    sample_id: str
    kind: str
    company: str
    role: str
    source_name: str
    source_url: str
    snippet: str
    score: float


@dataclass
class LibrarySearchResult:
    ok: bool
    query: str
    hits: list[LibraryHit]
    error: str = ""

    def for_model(self) -> str:
        if self.error:
            return f"检索面经失败：{self.error}"
        if not self.hits:
            return f"检索「{self.query}」没有命中。不要编一串大题，只问当前方向的下一个微步骤。"
        lines = [f"检索「{self.query}」命中 {len(self.hits)} 条原文（按相关度）："]
        for index, hit in enumerate(self.hits, start=1):
            lines.append(
                f"{index}. [{hit.sample_id}] {hit.company}/{hit.role} · {hit.source_name}："
                f"{hit.snippet}"
            )
        lines.append("下一问只选其中一件事来问，保留原问的具体点，不要合并成清单。")
        return "\n".join(lines)

    def for_public(self) -> str:
        if self.error:
            return "面经检索暂不可用。"
        if not self.hits:
            return "没有检索到与当前话题相关的面经"
        return f"检索到 {len(self.hits)} 条相关面经"

    def public_hits(self) -> list[dict[str, str]]:
        return [
            {
                "id": hit.sample_id,
                "kind": hit.kind,
                "company": hit.company,
                "role": hit.role,
                "source": hit.source_name,
                "url": hit.source_url,
                "snippet": hit.snippet,
            }
            for hit in self.hits
        ]


def _tokenize(text: str) -> list[str]:
    lowered = (text or "").lower()
    tokens = LATIN_TOKEN.findall(lowered)
    cjk = CJK_CHAR.findall(lowered)
    tokens.extend("".join(pair) for pair in zip(cjk, cjk[1:]))
    return tokens


def _trim_original(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) <= SNIPPET_CHARS:
        return cleaned
    return cleaned[: SNIPPET_CHARS - 1] + "…"


def _split_interview_snippets(sample: dict[str, Any]) -> list[str]:
    text = str(sample.get("text") or "").strip()
    snippets: list[str] = []
    for match in NUMBERED_ITEM.finditer(text):
        piece = re.sub(r"\s+", " ", match.group(1)).strip()
        if 6 <= len(piece) <= 180:
            snippets.append(piece)
    for match in QUESTION_SENTENCE.finditer(text):
        piece = match.group(0).strip()
        if piece not in snippets:
            snippets.append(piece)
    extras = [
        str(sample.get("question_types") or "").strip(),
        str(sample.get("experience") or "").strip(),
        str(sample.get("requirements") or "").strip(),
    ]
    for extra in extras:
        if extra and extra not in snippets:
            snippets.append(extra)
    if not snippets and text:
        snippets.append(text)
    return snippets


def _iter_samples() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename in ("interviews.json", "jds.json"):
        path = JD_DIR / filename
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
    return rows


@lru_cache(maxsize=1)
def _load_index(cache_key: tuple[tuple[str, int], ...]) -> tuple[list[LibraryChunk], dict[str, int]]:
    _ = cache_key
    chunks: list[LibraryChunk] = []
    df: dict[str, int] = {}
    for sample in _iter_samples():
        kind = str(sample.get("kind") or "").strip().lower()
        if kind not in {"jd", "interview"}:
            kind = "interview" if "interview" in str(sample.get("id") or "") else "jd"
        for snippet in _split_interview_snippets(sample):
            tokens = tuple(_tokenize(snippet + " " + str(sample.get("role") or "")))
            if not tokens:
                continue
            chunks.append(
                LibraryChunk(
                    sample_id=str(sample.get("id") or ""),
                    kind=kind,
                    company=str(sample.get("company") or ""),
                    role=str(sample.get("role") or ""),
                    source_name=str(sample.get("source_name") or ""),
                    source_url=str(sample.get("source_url") or ""),
                    snippet=_trim_original(snippet),
                    tokens=tokens,
                )
            )
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
    return chunks, df


def _index_cache_key() -> tuple[tuple[str, int], ...]:
    keys: list[tuple[str, int]] = []
    for filename in ("interviews.json", "jds.json"):
        path = JD_DIR / filename
        keys.append((filename, int(path.stat().st_mtime) if path.exists() else 0))
    return tuple(keys)


def _score_chunk(
    chunk: LibraryChunk,
    query_tokens: list[str],
    df: dict[str, int],
    corpus_size: int,
) -> float:
    if not query_tokens or not chunk.tokens:
        return 0.0
    tf: dict[str, int] = {}
    for token in chunk.tokens:
        tf[token] = tf.get(token, 0) + 1
    score = 0.0
    length = max(len(chunk.tokens), 1)
    for token in query_tokens:
        freq = tf.get(token, 0)
        if not freq:
            continue
        idf = log((corpus_size - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5) + 1.0)
        score += idf * (freq * 2.2) / (freq + 1.2 * (0.25 + 0.75 * length / 40))
    return score


def is_unsearchable_query(query: str) -> bool:
    """True for process talk that must not hit the interview corpus."""

    compact = re.sub(r"\s+", "", query or "")
    if len(compact) < 4:
        return True
    return bool(PROCESS_QUERY.search(compact))


def search_library(
    query: str,
    *,
    kind: str = "interview",
    limit: int = MAX_HITS,
) -> LibrarySearchResult:
    cleaned = (query or "").strip()
    if not cleaned:
        return LibrarySearchResult(ok=False, query="", hits=[], error=ERROR_EMPTY_QUERY)
    if is_unsearchable_query(cleaned):
        return LibrarySearchResult(ok=True, query=cleaned, hits=[])

    chunks, df = _load_index(_index_cache_key())
    wanted = (kind or "interview").strip().lower()
    if wanted not in {"interview", "jd", "any"}:
        wanted = "interview"
    pool = [chunk for chunk in chunks if wanted == "any" or chunk.kind == wanted]
    if not pool:
        pool = chunks

    query_tokens = _tokenize(cleaned)
    scored: list[LibraryHit] = []
    seen: set[str] = set()
    for chunk in pool:
        score = _score_chunk(chunk, query_tokens, df, max(len(pool), 1))
        if score <= 0:
            continue
        fingerprint = f"{chunk.sample_id}:{chunk.snippet[:80]}"
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        scored.append(
            LibraryHit(
                sample_id=chunk.sample_id,
                kind=chunk.kind,
                company=chunk.company,
                role=chunk.role,
                source_name=chunk.source_name,
                source_url=chunk.source_url,
                snippet=chunk.snippet,
                score=score,
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    strong = [hit for hit in scored if hit.score >= MIN_HIT_SCORE][: max(0, limit)]
    return LibrarySearchResult(ok=True, query=cleaned, hits=strong)


def topic_search_query(
    *,
    direction_title: str,
    last_question: str,
    answer: str,
) -> str:
    """Build a topic query. Process talk like「请继续问吧」is not used as the query."""

    parts: list[str] = []
    cleaned_answer = re.sub(r"\s+", " ", (answer or "").strip())
    if cleaned_answer and not is_unsearchable_query(cleaned_answer):
        parts.append(cleaned_answer[:80])
    cleaned_question = re.sub(r"\s+", " ", (last_question or "").strip())
    if cleaned_question:
        parts.append(cleaned_question[:80])
    elif (direction_title or "").strip():
        parts.append(direction_title.strip()[:40])
    return " ".join(part for part in parts if part).strip()[:120]


def run_search_library_from_tool_args(
    arguments: Mapping[str, object] | None,
) -> LibrarySearchResult:
    payload = arguments if isinstance(arguments, Mapping) else {}
    query = payload.get("query", "")
    kind = payload.get("kind", "interview")
    return search_library(
        query if isinstance(query, str) else "",
        kind=kind if isinstance(kind, str) else "interview",
    )


