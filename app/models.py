"""Validated API and agent data models."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.repository import validate_github_url


CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
CODE_COORDINATE = re.compile(
    r"(?:[\w./-]+\.(?:py|js|ts|tsx|java|go|rs|cpp|c|h))(?::\d+)?",
    re.IGNORECASE,
)
BROAD_FIRST_QUESTION = re.compile(
    r"完整|整体|全流程|每一步|全部|详细介绍|系统讲|哪几步|分别|以及|同时|还是"
)


def _validate_user_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name}不能为空")
    if CONTROL_CHARACTERS.search(cleaned):
        raise ValueError(f"{field_name}不能包含控制字符")
    return cleaned


class SessionCreate(BaseModel):
    github_url: str = Field(min_length=1, max_length=512)
    statement: str = Field(min_length=1, max_length=8000)
    role: Literal["llm-algo", "training", "rag"]

    @field_validator("github_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        cleaned = _validate_user_text(value, "GitHub URL")
        return validate_github_url(cleaned)

    @field_validator("statement")
    @classmethod
    def validate_statement(cls, value: str) -> str:
        return _validate_user_text(value, "项目陈述")


class Direction(BaseModel):
    id: str = Field(min_length=2, max_length=16, pattern=r"^d[1-5]$")
    title: str = Field(min_length=2, max_length=80)
    goal: str = Field(min_length=4, max_length=240)

    @field_validator("title", "goal")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _validate_user_text(value, "方向内容")


class DirectionPlan(BaseModel):
    directions: list[Direction] = Field(min_length=3, max_length=5)
    first_question: str = Field(min_length=4, max_length=120)

    @field_validator("first_question")
    @classmethod
    def validate_first_question(cls, value: str) -> str:
        cleaned = _validate_user_text(value, "第一问")
        if CODE_COORDINATE.search(cleaned):
            raise ValueError("第一问不能包含代码文件名或行号")
        question_marks = cleaned.count("？") + cleaned.count("?")
        if BROAD_FIRST_QUESTION.search(cleaned) or question_marks > 1:
            raise ValueError("第一问必须只问方向 d1 的一个起始步骤")
        return cleaned

    @model_validator(mode="after")
    def validate_direction_sequence(self) -> "DirectionPlan":
        expected_ids = [f"d{index}" for index in range(1, len(self.directions) + 1)]
        actual_ids = [direction.id for direction in self.directions]
        if actual_ids != expected_ids:
            raise ValueError("方向 id 必须从 d1 开始连续排列")
        return self


class SessionCreated(BaseModel):
    id: str
    directions: list[Direction]
    first_question: str
    clone_ok: bool
    clone_error: str | None


class TurnCreate(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        return _validate_user_text(value, "回答")


class CodeSubmissionCreate(BaseModel):
    exercise_id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=32000)

    @field_validator("exercise_id")
    @classmethod
    def validate_exercise_id(cls, value: str) -> str:
        return _validate_user_text(value, "题目 id")

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return _validate_user_text(value, "代码")


class TurnResult(BaseModel):
    thought: str = Field(min_length=8, max_length=4000)
    direction_done: bool
    next_question: str = Field(min_length=4, max_length=360)

    @field_validator("thought", "next_question")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _validate_user_text(value, "轮次内容")

    @field_validator("next_question")
    @classmethod
    def validate_next_question(cls, value: str) -> str:
        cleaned = _validate_user_text(value, "下一问")
        if CODE_COORDINATE.search(cleaned):
            raise ValueError("下一问不能包含代码文件名或行号")
        return cleaned

    @model_validator(mode="after")
    def validate_thought_structure(self) -> "TurnResult":
        lowered = self.thought.lower()
        if "评价" not in self.thought:
            raise ValueError("思考必须包含评价")
        if "查代码" not in self.thought and "查代码" not in lowered:
            raise ValueError("思考必须说明是否查代码")
        if "本方向结束" not in self.thought:
            raise ValueError("思考必须说明本方向是否结束")
        forbidden = ("建议你", "总评", "复习", "岗位本质对照")
        if any(token in self.thought for token in forbidden):
            raise ValueError("思考不能包含建议或总评")
        return self
