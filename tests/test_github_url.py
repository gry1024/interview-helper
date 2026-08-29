"""GitHub repository URL allow-list regression tests."""

import pytest

from app.repository import validate_github_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://github.com/jingyaogong/minimind.git",
            "https://github.com/jingyaogong/minimind.git",
        ),
        (
            "https://github.com/openai/openai-python",
            "https://github.com/openai/openai-python",
        ),
        (
            "https://GITHUB.com/owner/repo",
            "https://github.com/owner/repo",
        ),
    ],
)
def test_accepts_canonical_github_repository_urls(url: str, expected: str) -> None:
    assert validate_github_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://gitlab.com/owner/repo",
        "https://github.com.evil.example/owner/repo",
        "https://user:password@github.com/owner/repo",
        "https://github.com:443/owner/repo",
        "https://github.com/owner",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner/repo/",
        "https://github.com/owner/repo?tab=readme",
        "https://github.com/owner/repo#readme",
        "https://github.com/owner%2Frepo",
        "ssh://git@github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
    ],
)
def test_rejects_non_repository_or_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_github_url(url)
