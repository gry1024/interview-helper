"""Teacher agent: side-hint only, never replaces the student's answer."""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.llm import LLMError, complete_json_with_tools
from app.models import TeacherHintResult
from app.tools.code_inspect import CODE_INSPECT_TOOL, run_code_inspect_from_tool_args


APP_DIR = Path(__file__).resolve().parent


def _latest_interviewer_question(turns: list[dict[str, Any]]) -> str:
    for turn in reversed(turns):
        if turn.get("role") == "interviewer":
            return str(turn.get("body") or "").strip()
    return ""


def write_teacher_hint(
    *,
    session: dict[str, Any],
    turns: list[dict[str, Any]],
    question: str | None = None,
) -> tuple[TeacherHintResult, dict[str, list[dict[str, Any]]]]:
    """Produce a reference hint for the current question. Not a turn."""

    teacher = (APP_DIR / "prompts" / "teacher.md").read_text(encoding="utf-8")
    current_question = (question or "").strip() or _latest_interviewer_question(turns)
    if not current_question:
        raise LLMError("当前没有可求助的面试问题")

    system_prompt = f"""
{teacher}

本场岗位：{session.get("role")}
项目陈述 JSON：{json.dumps(session.get("statement") or "", ensure_ascii=False)}
当前方向 id：{session.get("current_direction_id")}
仓库不在上下文中。需要对照实现时才调用 code_inspect。禁止把路径行号写进 hint。
""".strip()
    history = []
    for turn in turns[-12:]:
        role = turn.get("role")
        if role == "interviewer":
            history.append(f"面试官: {turn.get('body')}")
        elif role == "user":
            history.append(f"学生: {turn.get('body')}")
    user_prompt = f"""
最近对话：
{chr(10).join(history) or "（尚无学生回答）"}

学生现在卡在这一问，向老师求助：
{json.dumps(current_question, ensure_ascii=False)}

只给这一问的参考答案。不要出下一问。
""".strip()

    tool_events: list[dict[str, Any]] = []
    tool_meta: list[dict[str, Any]] = []

    def run_tool(name: str, args: dict[str, Any]) -> str:
        if name != "code_inspect":
            text = "老师只能使用 code_inspect。"
            tool_meta.append({"name": name, "args": args, "result": text})
            tool_events.append({"name": name, "args": args, "result": text})
            return text
        inspect = run_code_inspect_from_tool_args(
            session["id"],
            args,
            clone_ok=session.get("clone_ok"),
        )
        model_text = inspect.for_model()
        public_text = inspect.for_public()
        tool_meta.append({"name": name, "args": args, "result": model_text})
        tool_events.append({"name": name, "args": args, "result": public_text})
        return model_text

    raw = complete_json_with_tools(
        system_prompt,
        user_prompt,
        tools=[CODE_INSPECT_TOOL],
        run_tool=run_tool,
    )
    try:
        result = TeacherHintResult.model_validate(raw)
    except ValidationError as exc:
        raise LLMError("Teacher hint did not match the contract") from exc

    looked = result.looked_at_code or any(
        event.get("name") == "code_inspect" for event in tool_events
    )
    if looked != result.looked_at_code:
        result = result.model_copy(update={"looked_at_code": looked})
    return result, {"events": tool_events, "meta": tool_meta}
