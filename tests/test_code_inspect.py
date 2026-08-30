"""Sandboxed code_inspect tests.

标准样本对照（不必 clone 公网仓）：陈述含 RoPE / RMSNorm / SwiGLU /
Tokenizer / SFT / DPO。回答若吹 rerank / 万卡，应被本 tool 证伪；
public_hint 与下一问仍不得出现文件名或行号。
"""

from pathlib import Path

import pytest

from app import repository
from app.tools.code_inspect import (
    CODE_COORDINATE,
    ERROR_BAD_PATH,
    ERROR_REPO_UNAVAILABLE,
    ERROR_SESSION_MISSING,
    InspectLimits,
    code_inspect,
    run_code_inspect_from_tool_args,
)


STATEMENT_TERMS = ("RoPE", "RMSNorm", "SwiGLU", "Tokenizer", "SFT", "DPO")


def _write_minimind_fixture(root: Path) -> None:
    (root / "model.py").write_text(
        """
class RMSNorm:
    def forward(self, x):
        return x

def apply_rope(q, k):
    # RoPE rotary position embedding
    return q, k

def swiglu(x):
    return x
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "tokenizer.py").write_text(
        "class Tokenizer:\n    def encode(self, text):\n        return []\n",
        encoding="utf-8",
    )
    (root / "train_sft.py").write_text("# SFT supervised fine-tune loop\n", encoding="utf-8")
    (root / "train_dpo.py").write_text("# DPO preference alignment\n", encoding="utf-8")
    (root / "README.md").write_text("MiniMind decoder-only LLaMA-like\n", encoding="utf-8")


@pytest.fixture
def session_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    repos = tmp_path / "repos"
    monkeypatch.setattr(repository, "REPOS_DIR", repos)
    session_id = "session-minimind"
    root = repos / session_id
    root.mkdir(parents=True)
    _write_minimind_fixture(root)
    return session_id, root


def test_legal_read_matches_statement_terms(session_repo: tuple[str, Path]) -> None:
    session_id, _root = session_repo
    for term in STATEMENT_TERMS:
        result = code_inspect(session_id, term)
        assert result.ok
        assert result.available
        assert result.error is None
        assert term in result.conclusion
        assert "能对应" in result.conclusion
        assert CODE_COORDINATE.search(result.public_hint) is None
        assert "追问只谈能力与证据" in result.public_hint


def test_falsifies_rerank_and_10k_gpu_claims(session_repo: tuple[str, Path]) -> None:
    session_id, _root = session_repo
    result = code_inspect(session_id, "rerank 万卡")
    assert result.ok
    assert "未体现" in result.conclusion
    assert "rerank" in result.conclusion
    assert "万卡" in result.conclusion
    assert result.hit_count == 0
    assert CODE_COORDINATE.search(result.public_hint) is None
    assert CODE_COORDINATE.search(result.for_public()) is None
    assert ".py:" not in result.for_public()


def test_rejects_parent_escape_in_path_hint(session_repo: tuple[str, Path]) -> None:
    session_id, _root = session_repo
    result = code_inspect(session_id, "RoPE", path_hint="../etc/passwd")
    assert not result.ok
    assert result.error == ERROR_BAD_PATH
    assert result.internal_excerpt == ""
    assert "root:x:" not in (result.for_model() + result.public_hint)


def test_rejects_absolute_etc_path(session_repo: tuple[str, Path]) -> None:
    session_id, _root = session_repo
    result = code_inspect(session_id, "root", path_hint="/etc/passwd")
    assert not result.ok
    assert result.error == ERROR_BAD_PATH
    assert result.internal_excerpt == ""
    assert "root:x:" not in result.for_model()


def test_rejects_session_id_escape(session_repo: tuple[str, Path]) -> None:
    _session_id, _root = session_repo
    result = code_inspect("..", "RoPE")
    assert not result.ok
    assert result.error == ERROR_SESSION_MISSING
    assert result.internal_excerpt == ""


def test_rejects_symlink_escape(session_repo: tuple[str, Path]) -> None:
    session_id, root = session_repo
    escape = root / "escape"
    try:
        escape.symlink_to("/etc/passwd")
    except OSError:
        pytest.skip("无法创建指向仓外的符号链接")

    result = code_inspect(session_id, "root", path_hint="escape")
    assert not result.ok
    assert result.error == ERROR_BAD_PATH
    assert result.internal_excerpt == ""

    walked = code_inspect(session_id, "root:x:")
    assert "root:x:" not in walked.internal_excerpt


def test_rejects_git_dir_hint(session_repo: tuple[str, Path]) -> None:
    session_id, root = session_repo
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("secret_should_not_leak = 1\n", encoding="utf-8")
    result = code_inspect(session_id, "secret_should_not_leak", path_hint=".git/config")
    assert not result.ok
    assert result.error == ERROR_BAD_PATH
    scanned = code_inspect(session_id, "secret_should_not_leak")
    assert "未体现" in scanned.conclusion
    assert scanned.hit_count == 0
    assert "[摘录]" not in scanned.internal_excerpt
    assert "secret_should_not_leak =" not in scanned.internal_excerpt


def test_missing_session(session_repo: tuple[str, Path]) -> None:
    _session_id, _root = session_repo
    result = code_inspect("no-such-session", "RoPE")
    assert not result.ok
    assert not result.available
    assert result.error == ERROR_SESSION_MISSING
    assert "不存在" in result.error
    assert result.internal_excerpt == ""


def test_clone_ok_false_skips_disk(session_repo: tuple[str, Path]) -> None:
    session_id, _root = session_repo
    result = code_inspect(session_id, "RoPE", clone_ok=False)
    assert not result.ok
    assert result.error == ERROR_REPO_UNAVAILABLE
    assert result.internal_excerpt == ""


def test_skips_oversize_file(session_repo: tuple[str, Path]) -> None:
    session_id, root = session_repo
    unique = "UNIQUE_OVERSIZE_TOKEN"
    (root / "huge.py").write_text((unique + "\n") * 200, encoding="utf-8")
    result = code_inspect(
        session_id,
        unique,
        limits=InspectLimits(max_file_bytes=40),
    )
    assert result.ok
    assert "未体现" in result.conclusion
    assert result.hit_count == 0
    assert "[摘录]" not in result.internal_excerpt


def test_max_files_truncates(session_repo: tuple[str, Path]) -> None:
    session_id, root = session_repo
    unique = "UNIQUE_FILE_LIMIT"
    for index in range(3):
        (root / f"extra_{index}.txt").write_text(f"{unique} {index}\n", encoding="utf-8")
    result = code_inspect(
        session_id,
        unique,
        limits=InspectLimits(max_files=1),
    )
    assert result.ok
    assert result.truncated


def test_output_char_cap(session_repo: tuple[str, Path]) -> None:
    session_id, root = session_repo
    (root / "long.py").write_text("RoPE " * 400 + "\n", encoding="utf-8")
    result = code_inspect(
        session_id,
        "RoPE",
        limits=InspectLimits(max_output_chars=80),
    )
    assert result.ok
    assert len(result.internal_excerpt) <= 80
    assert result.internal_excerpt.endswith("…(已截断)")


def test_timeout_stops_scan(session_repo: tuple[str, Path]) -> None:
    session_id, _root = session_repo
    ticks = iter((0.0, 50.0, 50.0))
    result = code_inspect(
        session_id,
        "RoPE",
        limits=InspectLimits(timeout_sec=1),
        clock=lambda: next(ticks),
    )
    assert result.ok
    assert result.truncated
    assert "超时" in result.conclusion


def test_path_hint_narrows_to_existing_file(session_repo: tuple[str, Path]) -> None:
    session_id, _root = session_repo
    result = code_inspect(session_id, "Tokenizer", path_hint="tokenizer.py")
    assert result.ok
    assert "Tokenizer" in result.conclusion
    assert "tokenizer.py" in result.internal_excerpt
    assert CODE_COORDINATE.search(result.public_hint) is None


def test_tool_args_bind_server_session(session_repo: tuple[str, Path]) -> None:
    session_id, _root = session_repo
    result = run_code_inspect_from_tool_args(
        session_id,
        {"query": "SwiGLU", "path_hint": ""},
    )
    assert result.ok
    assert "SwiGLU" in result.conclusion
