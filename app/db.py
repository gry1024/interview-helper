"""SQLite connection, schema initialization, and session persistence."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
_write_lock = Lock()


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                github_url TEXT NOT NULL,
                statement TEXT NOT NULL,
                role TEXT NOT NULL,
                directions_json TEXT NOT NULL,
                current_direction_id TEXT NOT NULL,
                clone_path TEXT,
                clone_ok INTEGER NOT NULL DEFAULT 0
                    CHECK (clone_ok IN (0, 1)),
                status TEXT NOT NULL
                    CHECK (status IN ('ready', 'live', 'ended')),
                first_question TEXT NOT NULL
            )
            """
        )
        connection.commit()


def create_session(
    *,
    session_id: str,
    github_url: str,
    statement: str,
    role: str,
    directions: list[dict[str, str]],
    clone_path: str | None,
    clone_ok: bool,
    first_question: str,
) -> None:
    directions_json = json.dumps(
        directions,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    created_at = datetime.now(timezone.utc).isoformat()

    with _write_lock, closing(connect()) as connection:
        connection.execute(
            """
            INSERT INTO sessions (
                id, created_at, github_url, statement, role, directions_json,
                current_direction_id, clone_path, clone_ok, status,
                first_question
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                created_at,
                github_url,
                statement,
                role,
                directions_json,
                directions[0]["id"],
                clone_path,
                int(clone_ok),
                "live",
                first_question,
            ),
        )
        connection.commit()


def get_session(session_id: str) -> dict[str, Any] | None:
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    if row is None:
        return None

    session = dict(row)
    session["directions"] = json.loads(session.pop("directions_json"))
    session["clone_ok"] = bool(session["clone_ok"])
    return session
