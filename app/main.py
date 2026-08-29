"""FastAPI entry point for the Interview Helper web application."""

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
JD_DIR = ROOT_DIR / "app" / "jd"

app = FastAPI(title="Interview Helper")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a small readiness response for local and public checks."""

    return {"status": "ok"}


def _load_samples(filename: str) -> list[dict[str, Any]]:
    with (JD_DIR / filename).open(encoding="utf-8") as source_file:
        samples = json.load(source_file)

    return [
        sample
        for sample in samples
        if sample.get("source_url") and sample.get("source_name")
    ]


@app.get("/api/jds")
def list_job_samples() -> dict[str, list[dict[str, Any]]]:
    """Return only sourced JD and interview samples."""

    return {
        "jds": _load_samples("jds.json"),
        "interviews": _load_samples("interviews.json"),
    }


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
