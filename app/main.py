"""FastAPI entry point for the Interview Helper web application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

app = FastAPI(title="Interview Helper")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a small readiness response for local and public checks."""

    return {"status": "ok"}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
