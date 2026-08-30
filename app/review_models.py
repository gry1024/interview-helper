"""Pydantic models for the end-of-interview review snapshot.

Isolated from app.models so step 3 session/turn contracts stay untouched.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DirectionSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    goal: str


class ReviewSession(BaseModel):
    """Session fields frozen at the end moment. status is always ended."""

    model_config = ConfigDict(extra="allow")

    id: str
    created_at: str
    github_url: str
    statement: str
    role: str
    directions: list[DirectionSnapshot]
    current_direction_id: str
    clone_path: str | None = None
    clone_ok: bool
    status: Literal["ended"] = "ended"
    first_question: str


class ReviewTurn(BaseModel):
    """One persisted turn, body kept verbatim."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    session_id: str
    seq: int
    role: Literal["interviewer", "user", "thought"]
    body: str
    direction_id: str | None = None
    meta: Any = None


class ReviewReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str = Field(min_length=1)


class ReviewHelp(BaseModel):
    """One teacher-hint request, frozen for end-report evaluation."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    session_id: str | None = None
    created_at: str | None = None
    question: str
    hint: str
    looked_at_code: bool = False
    inspect_public: str | None = None
    direction_id: str | None = None


class ReviewSnapshot(BaseModel):
    """Complete end-moment copy: session + all turns + full report.

    Replay reads this object only. Do not regenerate or rewrite it later.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: Literal[1] = 1
    session: ReviewSession
    turns: list[ReviewTurn]
    report: ReviewReport
    helps: list[ReviewHelp] = []


class ReviewListItem(BaseModel):
    id: str
    created_at: str
    statement_preview: str
    role: str
