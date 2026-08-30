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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                role TEXT NOT NULL
                    CHECK (role IN ('interviewer', 'user', 'thought')),
                body TEXT NOT NULL,
                direction_id TEXT,
                meta_json TEXT,
                UNIQUE(session_id, seq)
            )
            """
        )
        from app.db_reviews import init_reviews_table

        init_reviews_table(connection)
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
        connection.execute(
            """
            INSERT INTO turns (
                session_id, seq, role, body, direction_id, meta_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                0,
                "interviewer",
                first_question,
                directions[0]["id"],
                None,
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


def list_turns(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as connection:
        rows = connection.execute(
            """
            SELECT * FROM turns
            WHERE session_id = ?
            ORDER BY seq ASC
            """,
            (session_id,),
        ).fetchall()

    turns: list[dict[str, Any]] = []
    for row in rows:
        turn = dict(row)
        turn["meta"] = json.loads(turn.pop("meta_json") or "null")
        turns.append(turn)
    return turns


def append_turn_bundle(
    *,
    session_id: str,
    user_answer: str,
    thought: str,
    next_question: str,
    direction_id: str,
    next_direction_id: str,
    meta: list[dict[str, Any]] | None = None,
    user_meta: dict[str, Any] | None = None,
) -> None:
    meta_json = (
        json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
        if meta
        else None
    )
    user_meta_json = (
        json.dumps(user_meta, ensure_ascii=False, separators=(",", ":"))
        if user_meta
        else None
    )

    with _write_lock, closing(connect()) as connection:
        current_seq = connection.execute(
            "SELECT COALESCE(MAX(seq), -1) FROM turns WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        user_seq = current_seq + 1
        thought_seq = current_seq + 2
        question_seq = current_seq + 3

        connection.execute(
            """
            INSERT INTO turns (
                session_id, seq, role, body, direction_id, meta_json
            )
            VALUES (?, ?, 'user', ?, ?, ?)
            """,
            (session_id, user_seq, user_answer, direction_id, user_meta_json),
        )
        connection.execute(
            """
            INSERT INTO turns (
                session_id, seq, role, body, direction_id, meta_json
            )
            VALUES (?, ?, 'thought', ?, ?, ?)
            """,
            (session_id, thought_seq, thought, direction_id, meta_json),
        )
        connection.execute(
            """
            INSERT INTO turns (
                session_id, seq, role, body, direction_id, meta_json
            )
            VALUES (?, ?, 'interviewer', ?, ?, NULL)
            """,
            (session_id, question_seq, next_question, next_direction_id),
        )
        connection.execute(
            """
            UPDATE sessions
            SET current_direction_id = ?, status = 'live'
            WHERE id = ?
            """,
            (next_direction_id, session_id),
        )
        connection.commit()


def mark_session_ended(session_id: str) -> None:
    """Mark a session ended. Prefer save_review_and_end_session for the real path."""

    with _write_lock, closing(connect()) as connection:
        connection.execute(
            "UPDATE sessions SET status = 'ended' WHERE id = ?",
            (session_id,),
        )
        connection.commit()


def save_review_and_end_session(
    *,
    session_id: str,
    report_text: str,
    snapshot_json: str,
    review_id: str | None = None,
) -> dict[str, Any]:
    """Freeze the review then set status=ended in the same write transaction."""

    from app.db_reviews import save_review

    with _write_lock, closing(connect()) as connection:
        review = save_review(
            session_id=session_id,
            report_text=report_text,
            snapshot_json=snapshot_json,
            review_id=review_id,
            connection=connection,
        )
        cursor = connection.execute(
            "UPDATE sessions SET status = 'ended' WHERE id = ?",
            (session_id,),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"session {session_id} 无法标记为已结束")
        connection.commit()
    return review
