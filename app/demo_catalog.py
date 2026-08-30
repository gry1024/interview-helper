"""Shared demo project catalog for the start form, tests, and accept scripts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent.parent / "static" / "demo-projects.json"


@lru_cache(maxsize=1)
def load_demo_catalog() -> list[dict[str, Any]]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    projects = payload.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ValueError("demo catalog is empty")
    return projects


def get_demo(demo_id: str) -> dict[str, Any]:
    for item in load_demo_catalog():
        if item.get("id") == demo_id:
            return item
    raise KeyError(demo_id)


def apply_demo_preset(demo_id: str, current_role: str | None = None) -> dict[str, str]:
    """Return form fields for a demo sample.

    GitHub URL and statement always come from the catalog. Role is pinned to the
    sample's `llm-algo` when the current select is empty; samples themselves
    are also llm-algo, so a filled other role is overwritten to match the sample.
    """
    demo = get_demo(demo_id)
    sample_role = str(demo.get("role") or "llm-algo")
    if (current_role or "").strip() and not sample_role:
        role = str(current_role).strip()
    else:
        role = sample_role
    return {
        "github_url": str(demo["github_url"]),
        "statement": str(demo["statement"]),
        "role": role,
    }
