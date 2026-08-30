"""Demo catalog presets: MiniMind + nano-vLLM fill the start form."""

from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import threading

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
import pytest

from app.demo_catalog import apply_demo_preset, get_demo, load_demo_catalog
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
PLAN_DOC = ROOT / "docs" / "开发计划.md"


def _plan_minimind_statement() -> str:
    for line in PLAN_DOC.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("> MiniMind:"):
            return stripped[2:].strip()
    raise AssertionError("开发计划.md 缺少 MiniMind 原样陈述")


def test_minimind_catalog_matches_development_plan() -> None:
    demo = get_demo("minimind")
    assert demo["github_url"] == "https://github.com/jingyaogong/minimind.git"
    assert demo["role"] == "llm-algo"
    assert demo["statement"] == _plan_minimind_statement()


def test_nano_vllm_catalog_keeps_user_metrics() -> None:
    demo = get_demo("nano-vllm")
    assert demo["github_url"] == "https://github.com/GeeeekExplorer/nano-vllm.git"
    assert demo["role"] == "llm-algo"
    statement = demo["statement"]
    for needle in (
        "Triton",
        "Chunked Prefill",
        "FP8",
        "CUDAGraph",
        "PagedAttention",
        "Flash Attention",
        "Qwen3-0.6B",
        "eager",
        "P99",
        "Gather",
        "Softmax",
    ):
        assert needle in statement
    assert "cager" not in statement
    assert "CUDAGraphh" not in statement
    assert "Sofmax" not in statement
    assert "Gathert" not in statement
    assert "业化" not in statement


def test_apply_demo_preset_returns_repo_and_statement() -> None:
    for demo_id in ("minimind", "nano-vllm"):
        demo = get_demo(demo_id)
        filled = apply_demo_preset(demo_id, current_role="")
        assert filled["github_url"] == demo["github_url"]
        assert filled["statement"] == demo["statement"]
        assert filled["role"] == "llm-algo"
        overwritten = apply_demo_preset(demo_id, current_role="rag")
        assert overwritten["role"] == "llm-algo"
        assert overwritten["github_url"] == demo["github_url"]


def test_demo_catalog_has_exactly_two_samples() -> None:
    ids = [item["id"] for item in load_demo_catalog()]
    assert ids == ["minimind", "nano-vllm"]


def test_demo_projects_json_is_served() -> None:
    client = TestClient(app)
    response = client.get("/demo-projects.json")
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["projects"]] == ["minimind", "nano-vllm"]


class _StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@pytest.fixture
def static_origin() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = ThreadingHTTPServer(("127.0.0.1", port), _StaticHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_clicking_demo_buttons_fills_github_and_statement(static_origin: str) -> None:
    minimind = apply_demo_preset("minimind")
    nano = apply_demo_preset("nano-vllm")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(static_origin, wait_until="domcontentloaded")
        page.wait_for_selector("#demo-minimind")
        page.wait_for_selector("#demo-nano-vllm")
        page.wait_for_function(
            "() => (window.__interviewHelper?.getDemoCatalog() || []).length >= 2"
        )

        assert page.locator("#demo-minimind").inner_text().strip() == "试用 MiniMind"
        assert page.locator("#demo-nano-vllm").inner_text().strip() == "试用 nano-vLLM"
        assert page.locator("#start-session").is_visible()
        assert page.input_value("#github-url") == ""
        assert page.input_value("#statement") == ""

        page.click("#demo-minimind")
        page.wait_for_function(
            "(url) => document.querySelector('#github-url').value === url",
            arg=minimind["github_url"],
        )
        assert page.input_value("#github-url") == minimind["github_url"]
        assert page.input_value("#statement") == minimind["statement"]
        assert page.input_value("#role") == "llm-algo"
        assert "active" in (page.get_attribute("#demo-minimind", "class") or "")
        assert "active" not in (page.get_attribute("#demo-nano-vllm", "class") or "")

        page.click("#demo-nano-vllm")
        page.wait_for_function(
            "(url) => document.querySelector('#github-url').value === url",
            arg=nano["github_url"],
        )
        assert page.input_value("#github-url") == nano["github_url"]
        assert page.input_value("#statement") == nano["statement"]
        assert "Triton" in page.input_value("#statement")
        assert "Chunked Prefill" in page.input_value("#statement")
        assert "FP8" in page.input_value("#statement")
        assert "active" in (page.get_attribute("#demo-nano-vllm", "class") or "")
        assert "active" not in (page.get_attribute("#demo-minimind", "class") or "")

        page.click("#demo-minimind")
        page.wait_for_function(
            "(url) => document.querySelector('#github-url').value === url",
            arg=minimind["github_url"],
        )
        assert page.input_value("#github-url") == minimind["github_url"]
        assert page.input_value("#statement") == minimind["statement"]

        start_box = page.locator("#start-session").bounding_box()
        assert start_box is not None
        assert start_box["y"] + start_box["height"] <= 900
        demo_box = page.locator(".demo-strip").bounding_box()
        assert demo_box is not None
        assert demo_box["y"] >= 0
        browser.close()
