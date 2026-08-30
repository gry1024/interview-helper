"""Sandboxed, on-demand repository inspection for one interview session."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable, Mapping

from app import repository


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
DRIVE_HINT = re.compile(r"^[A-Za-z]:")
KEYWORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,}|[\u4e00-\u9fff]{2,}")
CODE_COORDINATE = re.compile(
    r"(?:[\w./\\-]+\.(?:py|js|ts|tsx|jsx|java|go|rs|cpp|cc|c|h|md|txt|json|yml|yaml|toml))"
    r"(?::\d+)?",
    re.IGNORECASE,
)
LINE_COORDINATE = re.compile(r"\b(?:line|行号?)\s*\d+\b", re.IGNORECASE)
SKIP_DIR_NAMES = frozenset(
    {".git", "node_modules", "venv", ".venv", "__pycache__", ".tox"}
)
BINARY_SUFFIXES = frozenset(
    {
        ".pyc",
        ".pyo",
        ".so",
        ".o",
        ".a",
        ".bin",
        ".pkl",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".woff",
        ".woff2",
        ".ttf",
        ".zip",
        ".gz",
        ".whl",
    }
)

ERROR_SESSION_MISSING = "会话不存在或仓库不可用"
ERROR_REPO_UNAVAILABLE = "仓库不可用"
ERROR_BAD_PATH = "路径不合法"
ERROR_EMPTY_QUERY = "查询不能为空"
ERROR_QUERY_TOO_LONG = "查询过长"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class InspectLimits:
    timeout_sec: float = _env_int("INSPECT_TIMEOUT_SEC", 8)
    max_files: int = _env_int("INSPECT_MAX_FILES", 400)
    max_file_bytes: int = _env_int("INSPECT_MAX_FILE_BYTES", 1 * 1024 * 1024)
    max_output_chars: int = _env_int("INSPECT_MAX_OUTPUT_CHARS", 6000)
    context_lines: int = 15
    max_hits: int = 8
    max_top_level: int = 40
    max_query_chars: int = 500


@dataclass(frozen=True)
class CodeInspectResult:
    ok: bool
    available: bool
    conclusion: str
    public_hint: str
    internal_excerpt: str
    error: str | None
    hit_count: int = 0
    truncated: bool = False
    top_level: tuple[str, ...] = ()

    def for_model(self) -> str:
        """Excerpt and conclusion for the model only; already size-capped."""

        parts = [
            f"ok={self.ok}",
            f"available={self.available}",
        ]
        if self.error:
            parts.append(f"error={self.error}")
        if self.conclusion:
            parts.append(f"conclusion={self.conclusion}")
        if self.public_hint:
            parts.append(f"public_hint={self.public_hint}")
        if self.internal_excerpt:
            parts.extend(["internal_excerpt:", self.internal_excerpt])
        if self.truncated:
            parts.append("truncated=true")
        return _cap("\n".join(parts), 6000)

    def for_public(self) -> str:
        """Candidate-safe text: no filenames or line numbers."""

        pieces = [piece for piece in (self.conclusion, self.public_hint) if piece]
        if self.error and not pieces:
            pieces = [self.error]
        return _strip_coordinates(" ".join(pieces)).strip()


CODE_INSPECT_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "code_inspect",
        "description": (
            "按需核对本场已克隆的项目仓库。用于判断学生陈述是否属实、"
            "同一方向下一步往哪引、结束评估项目价值和提出改良建议。"
            "不要把返回的路径或行号写进给学生的下一问。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要核对的主张或关键词，例如 RoPE、SFT、rerank、万卡",
                },
                "path_hint": {
                    "type": "string",
                    "description": "可选的仓内相对路径提示；禁止 .. 与绝对路径",
                },
            },
            "required": ["query"],
        },
    },
}


class _InspectFail(Exception):
    def __init__(self, error: str, *, available: bool) -> None:
        super().__init__(error)
        self.error = error
        self.available = available


def code_inspect(
    session_id: str,
    query: str,
    path_hint: str | None = None,
    *,
    clone_ok: bool | None = None,
    limits: InspectLimits | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> CodeInspectResult:
    """Inspect one session clone and return excerpts, never the whole tree."""

    limits = limits or InspectLimits()
    try:
        cleaned_query = _validate_query(query, limits)
        if clone_ok is False:
            raise _InspectFail(ERROR_REPO_UNAVAILABLE, available=False)
        root = _session_root(session_id)
        scope = _resolve_path_hint(root, path_hint)
        return _search(root, scope, cleaned_query, limits, clock)
    except _InspectFail as exc:
        public = (
            "代码仓库暂不可用，本轮只能根据口头回答继续。"
            if not exc.available
            else "未能按提示核对仓库，忽略该路径或查询约束。"
        )
        if exc.error == ERROR_EMPTY_QUERY:
            public = "没有可核对的主张。"
        return CodeInspectResult(
            ok=False,
            available=exc.available,
            conclusion="",
            public_hint=_strip_coordinates(public),
            internal_excerpt="",
            error=exc.error,
        )


def run_code_inspect_from_tool_args(
    session_id: str,
    arguments: Mapping[str, object] | None,
    *,
    clone_ok: bool | None = None,
    limits: InspectLimits | None = None,
) -> CodeInspectResult:
    """Bind server-side session_id to a model tool-call payload."""

    payload = arguments if isinstance(arguments, Mapping) else {}
    query = payload.get("query", "")
    hint = payload.get("path_hint")
    path_hint = hint if isinstance(hint, str) else None
    return code_inspect(
        session_id,
        query if isinstance(query, str) else str(query or ""),
        path_hint,
        clone_ok=clone_ok,
        limits=limits,
    )


def _validate_query(query: str, limits: InspectLimits) -> str:
    if not isinstance(query, str):
        raise _InspectFail(ERROR_EMPTY_QUERY, available=True)
    cleaned = query.strip()
    if not cleaned:
        raise _InspectFail(ERROR_EMPTY_QUERY, available=True)
    if CONTROL_CHARACTERS.search(cleaned):
        raise _InspectFail(ERROR_EMPTY_QUERY, available=True)
    if len(cleaned) > limits.max_query_chars:
        raise _InspectFail(ERROR_QUERY_TOO_LONG, available=True)
    return cleaned


def _session_root(session_id: str) -> Path:
    if not isinstance(session_id, str):
        raise _InspectFail(ERROR_SESSION_MISSING, available=False)
    cleaned = session_id.strip()
    if (
        not cleaned
        or ".." in cleaned
        or "/" in cleaned
        or "\\" in cleaned
        or CONTROL_CHARACTERS.search(cleaned)
        or not SESSION_ID_RE.fullmatch(cleaned)
    ):
        raise _InspectFail(ERROR_SESSION_MISSING, available=False)

    repos = repository.REPOS_DIR.resolve()
    root = (repos / cleaned).resolve()
    if root.parent != repos:
        raise _InspectFail(ERROR_SESSION_MISSING, available=False)
    if not root.is_dir() or root.is_symlink():
        raise _InspectFail(ERROR_SESSION_MISSING, available=False)
    return root


def _resolve_path_hint(root: Path, path_hint: str | None) -> Path:
    if path_hint is None:
        return root
    if not isinstance(path_hint, str):
        raise _InspectFail(ERROR_BAD_PATH, available=True)
    hint = path_hint.strip()
    if not hint:
        return root
    if len(hint) > 512 or CONTROL_CHARACTERS.search(hint):
        raise _InspectFail(ERROR_BAD_PATH, available=True)
    if hint.startswith("~") or hint.startswith("/") or hint.startswith("\\"):
        raise _InspectFail(ERROR_BAD_PATH, available=True)
    if hint.startswith("//") or DRIVE_HINT.match(hint):
        raise _InspectFail(ERROR_BAD_PATH, available=True)
    if "%" in hint or ".." in hint:
        raise _InspectFail(ERROR_BAD_PATH, available=True)

    normalized = hint.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts) or any(
        part in SKIP_DIR_NAMES for part in parts
    ):
        raise _InspectFail(ERROR_BAD_PATH, available=True)

    candidate = root
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise _InspectFail(ERROR_BAD_PATH, available=True)

    resolved = candidate.resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise _InspectFail(ERROR_BAD_PATH, available=True) from exc
    if resolved.is_symlink():
        raise _InspectFail(ERROR_BAD_PATH, available=True)
    return resolved


def _search(
    root: Path,
    scope: Path,
    query: str,
    limits: InspectLimits,
    clock: Callable[[], float],
) -> CodeInspectResult:
    keywords = _keywords(query)
    top_level, top_truncated = _list_top_level(root, limits.max_top_level)
    found_counts = {keyword: 0 for keyword in keywords}
    windows: list[str] = []
    files_read = 0
    truncated = top_truncated
    deadline = clock() + limits.timeout_sec
    timed_out = False

    for file_path in _iter_files(scope, root):
        if clock() >= deadline:
            timed_out = True
            truncated = True
            break
        if files_read >= limits.max_files:
            truncated = True
            break

        text = _read_text_file(file_path, limits.max_file_bytes)
        files_read += 1
        if text is None:
            continue

        rel = _safe_relpath(file_path, root)
        name_blob = f"{rel} {file_path.name}"
        matched_here = False
        needles = keywords or (query,)
        for keyword in needles:
            in_name = keyword.lower() in name_blob.lower()
            in_body = keyword.lower() in text.lower()
            if not in_name and not in_body:
                continue
            matched_here = True
            if keyword in found_counts:
                found_counts[keyword] += 1

        if not matched_here:
            continue
        excerpt = _file_excerpt(rel, text, needles, limits.context_lines)
        if excerpt:
            windows.append(excerpt)
        if len(windows) >= limits.max_hits:
            truncated = True
            break

    conclusion = _conclusion(keywords, found_counts, len(windows), timed_out)
    public_hint = _public_hint(keywords, found_counts, len(windows), timed_out)
    internal = _internal_excerpt(top_level, conclusion, windows, limits.max_output_chars)
    return CodeInspectResult(
        ok=True,
        available=True,
        conclusion=conclusion,
        public_hint=public_hint,
        internal_excerpt=internal,
        error=None,
        hit_count=len(windows),
        truncated=truncated,
        top_level=top_level,
    )


def _keywords(query: str) -> tuple[str, ...]:
    seen: list[str] = []
    for match in KEYWORD_RE.finditer(query):
        token = match.group(0)
        if token.lower() not in {item.lower() for item in seen}:
            seen.append(token)
    return tuple(seen)


def _list_top_level(root: Path, limit: int) -> tuple[tuple[str, ...], bool]:
    names: list[str] = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return (), False
    for entry in entries:
        if entry.name in SKIP_DIR_NAMES or entry.is_symlink():
            continue
        names.append(entry.name)
    truncated = len(names) > limit
    return tuple(names[:limit]), truncated


def _iter_files(scope: Path, root: Path) -> list[Path]:
    if scope.is_file() and not scope.is_symlink():
        return [scope] if _is_within(scope, root) else []
    if not scope.is_dir() or scope.is_symlink():
        return []

    files: list[Path] = []
    for current, directories, filenames in os.walk(scope, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink() or not _is_within(current_path, root):
            directories[:] = []
            continue
        directories[:] = sorted(
            name
            for name in directories
            if name not in SKIP_DIR_NAMES and not (current_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            file_path = current_path / filename
            if file_path.is_symlink() or not _is_within(file_path, root):
                continue
            files.append(file_path)
    return files


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _safe_relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


def _read_text_file(path: Path, max_bytes: int) -> str | None:
    try:
        file_stat = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(file_stat.st_mode) or stat.S_ISLNK(file_stat.st_mode):
        return None
    if path.suffix.lower() in BINARY_SUFFIXES:
        return None
    if file_stat.st_size > max_bytes:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _file_excerpt(
    rel: str,
    text: str,
    needles: tuple[str, ...],
    context_lines: int,
) -> str:
    lines = text.splitlines()
    hit_indexes: list[int] = []
    lowered_needles = tuple(needle.lower() for needle in needles)
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(needle in lowered for needle in lowered_needles):
            hit_indexes.append(index)
    if not hit_indexes:
        preview = lines[: min(len(lines), context_lines * 2 + 1)]
        numbered = _number_lines(preview, 1)
        return f"{rel}:1\n{numbered}"

    ranges: list[tuple[int, int]] = []
    for index in hit_indexes:
        start = max(0, index - context_lines)
        end = min(len(lines), index + context_lines + 1)
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))

    chunks: list[str] = []
    for start, end in ranges[:3]:
        numbered = _number_lines(lines[start:end], start + 1)
        chunks.append(f"{rel}:{start + 1}\n{numbered}")
    return "\n".join(chunks)


def _number_lines(lines: list[str], start: int) -> str:
    width = len(str(start + len(lines) - 1)) if lines else 1
    return "\n".join(
        f"{index:>{width}} | {line}"
        for index, line in enumerate(lines, start=start)
    )


def _conclusion(
    keywords: tuple[str, ...],
    found_counts: dict[str, int],
    hit_count: int,
    timed_out: bool,
) -> str:
    prefix = "检索超时，仅基于已扫描文件。" if timed_out else ""
    if keywords:
        found = [keyword for keyword in keywords if found_counts.get(keyword, 0) > 0]
        missing = [keyword for keyword in keywords if found_counts.get(keyword, 0) == 0]
        parts: list[str] = []
        if found:
            parts.append("仓库中能对应：" + "、".join(found))
        if missing:
            parts.append("仓库中未体现：" + "、".join(missing))
        return _strip_coordinates(prefix + "；".join(parts) + "。")
    if hit_count:
        return _strip_coordinates(prefix + "仓库中存在与查询相关的摘录。")
    return _strip_coordinates(prefix + "仓库中未找到与查询相关的实现。")


def _public_hint(
    keywords: tuple[str, ...],
    found_counts: dict[str, int],
    hit_count: int,
    timed_out: bool,
) -> str:
    found = [keyword for keyword in keywords if found_counts.get(keyword, 0) > 0]
    missing = [keyword for keyword in keywords if found_counts.get(keyword, 0) == 0]
    bits: list[str] = []
    if timed_out:
        bits.append("核对未扫完整。")
    if found:
        bits.append("仓库能支持这些实现陈述：" + "、".join(found) + "。")
    if missing:
        bits.append("仓库未体现这些实现陈述：" + "、".join(missing) + "。")
    if not keywords:
        bits.append(
            "仓库里能找到相关实现。" if hit_count else "仓库里看不到与该回答对应的实现。"
        )
    bits.append("追问只谈能力与证据，不要点名文件或行号。")
    return _strip_coordinates("".join(bits))


def _internal_excerpt(
    top_level: tuple[str, ...],
    conclusion: str,
    windows: list[str],
    max_chars: int,
) -> str:
    lines = [
        "[顶层] " + (", ".join(top_level) if top_level else "(空)"),
        f"[结论] {conclusion}",
        f"[命中数] {len(windows)}",
    ]
    if windows:
        lines.append("[摘录]")
        lines.extend(windows)
    return _cap("\n".join(lines), max_chars)


def _cap(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker = "…(已截断)"
    keep = max(0, max_chars - len(marker))
    return text[:keep] + marker


def _strip_coordinates(text: str) -> str:
    cleaned = CODE_COORDINATE.sub("（实现位置已省略）", text)
    cleaned = LINE_COORDINATE.sub("行号已省略", cleaned)
    return cleaned
