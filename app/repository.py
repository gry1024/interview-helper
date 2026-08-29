"""Restricted GitHub repository cloning for interview sessions."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from urllib.parse import urlsplit

from app.config import settings


ROOT_DIR = Path(__file__).resolve().parent.parent
REPOS_DIR = ROOT_DIR / "repos"
GITHUB_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class CloneResult:
    path: str | None
    ok: bool
    error: str | None


def validate_github_url(value: str) -> str:
    """Validate and return a canonical, clone-safe GitHub HTTPS URL."""

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("GitHub URL 格式无效") from exc

    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "github.com":
        raise ValueError("只允许 https://github.com 仓库链接")
    if parsed.username or parsed.password or port is not None:
        raise ValueError("GitHub URL 不能包含凭据或端口")
    if parsed.query or parsed.fragment or "%" in parsed.path:
        raise ValueError("GitHub URL 不能包含查询、片段或编码路径")
    if parsed.path.endswith("/"):
        raise ValueError("GitHub URL 不能以斜杠结尾")

    parts = parsed.path.split("/")
    if len(parts) != 3 or not parts[1] or not parts[2]:
        raise ValueError("GitHub URL 必须只包含所有者和仓库名")

    owner, repository = parts[1], parts[2]
    repository_name = repository[:-4] if repository.endswith(".git") else repository
    if not repository_name:
        raise ValueError("GitHub 仓库名不能为空")
    if not GITHUB_COMPONENT.fullmatch(owner) or not GITHUB_COMPONENT.fullmatch(
        repository_name
    ):
        raise ValueError("GitHub 所有者或仓库名包含非法字符")

    suffix = ".git" if repository.endswith(".git") else ""
    return f"https://github.com/{owner}/{repository_name}{suffix}"


def _directory_size_bytes(path: Path) -> int:
    total = 0
    for root, directories, filenames in os.walk(path, followlinks=False):
        directories[:] = [
            name for name in directories if not (Path(root) / name).is_symlink()
        ]
        for filename in filenames:
            file_path = Path(root) / filename
            file_stat = file_path.lstat()
            if stat.S_ISREG(file_stat.st_mode):
                total += file_stat.st_size
    return total


def cleanup_session_repo(session_id: str) -> None:
    target = REPOS_DIR / session_id
    if target.parent.resolve() == REPOS_DIR.resolve():
        shutil.rmtree(target, ignore_errors=True)


def clone_repository(github_url: str, session_id: str) -> CloneResult:
    """Shallow-clone a validated repository into its locked session directory."""

    validated_url = validate_github_url(github_url)
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    target = REPOS_DIR / session_id
    if target.parent.resolve() != REPOS_DIR.resolve():
        return CloneResult(None, False, "仓库目标目录无效")

    cleanup_session_repo(session_id)
    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        validated_url,
        str(target),
    ]
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.clone_timeout_sec,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        cleanup_session_repo(session_id)
        return CloneResult(None, False, "仓库准备超时，代码核对暂不可用")
    except OSError:
        cleanup_session_repo(session_id)
        return CloneResult(None, False, "仓库准备失败，代码核对暂不可用")

    if completed.returncode != 0:
        cleanup_session_repo(session_id)
        return CloneResult(None, False, "仓库无法克隆，代码核对暂不可用")

    max_bytes = settings.clone_max_mb * 1024 * 1024
    if _directory_size_bytes(target) > max_bytes:
        cleanup_session_repo(session_id)
        return CloneResult(None, False, "仓库超过大小限制，代码核对暂不可用")

    return CloneResult(str(target), True, None)
