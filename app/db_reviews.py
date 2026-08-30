"""Isolated reviews table helpers. Do not import this from app.db yet.

Merge outline lives in docs/specs/2026-08-30-report.md.
This module must not UPDATE snapshot_json after the first insert.
"""

from contextlib import closing
from datetime import datetime, timezone
import sqlite3
from typing import Any

from app import db


REVIEWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    report_text TEXT NOT NULL,
    snapshot_json TEXT NOT NULL
)
"""


class ReviewAlreadyExistsError(ValueError):
    """A session may freeze exactly one review snapshot."""


def init_reviews_table(connection: sqlite3.Connection | None = None) -> None:
    if connection is not None:
        connection.execute(REVIEWS_TABLE_SQL)
        return

    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(db.connect()) as owned:
        owned.execute(REVIEWS_TABLE_SQL)
        owned.commit()


def save_review(
    *,
    session_id: str,
    report_text: str,
    snapshot_json: str,
    review_id: str | None = None,
) -> dict[str, Any]:
    """Insert the end-moment snapshot. Refuses to overwrite an existing row."""

    if not report_text:
        raise ValueError("report_text 不能为空")
    if not snapshot_json:
        raise ValueError("snapshot_json 不能为空")
    if report_text not in snapshot_json:
        raise ValueError("snapshot_json 必须包含报告全文")

    stored_id = review_id or session_id
    created_at = datetime.now(timezone.utc).isoformat()

    with db._write_lock, closing(db.connect()) as connection:
        try:
            connection.execute(
                """
                INSERT INTO reviews (
                    id, session_id, created_at, report_text, snapshot_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (stored_id, session_id, created_at, report_text, snapshot_json),
            )
        except sqlite3.IntegrityError as exc:
            raise ReviewAlreadyExistsError(
                f"session {session_id} 已有复盘，禁止事后重写"
            ) from exc
        connection.commit()

    return {
        "id": stored_id,
        "session_id": session_id,
        "created_at": created_at,
        "report_text": report_text,
        "snapshot_json": snapshot_json,
    }


def get_review(review_id: str) -> dict[str, Any] | None:
    """Return stored columns as-is. snapshot_json is the original string."""

    with closing(db.connect()) as connection:
        row = connection.execute(
            "SELECT * FROM reviews WHERE id = ?",
            (review_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def get_review_by_session(session_id: str) -> dict[str, Any] | None:
    with closing(db.connect()) as connection:
        row = connection.execute(
            "SELECT * FROM reviews WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def list_reviews() -> list[dict[str, str]]:
    """List cards only. Preview is derived at read time; stored JSON is not rewritten."""

    with closing(db.connect()) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at, snapshot_json
            FROM reviews
            ORDER BY created_at DESC
            """
        ).fetchall()

    items: list[dict[str, str]] = []
    for row in rows:
        payload = _preview_from_stored_json(row["snapshot_json"])
        items.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "statement_preview": payload["statement_preview"],
                "role": payload["role"],
            }
        )
    return items


def _preview_from_stored_json(snapshot_json: str) -> dict[str, str]:
    # Local import keeps db_reviews usable even if report helpers change.
    from app.report import load_review_for_replay, statement_preview

    snapshot = load_review_for_replay(snapshot_json)
    return {
        "statement_preview": statement_preview(snapshot.session.statement),
        "role": snapshot.session.role,
    }
