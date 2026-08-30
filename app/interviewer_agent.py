"""Read-only payload for the interviewer Agent transparency page.

All prompt strings are loaded from the same files `app.agent` uses.
Do not paraphrase them here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATIC_BUNDLE = Path(__file__).resolve().parent.parent / "static" / "interviewer-agent-data.js"

from app.agent import (
    MIN_INTERVIEWER_BEFORE_ABANDON,
    MIN_STUCK_BEFORE_ABANDON,
    MIN_TURNS_BEFORE_GOAL_DONE,
    STUCK_MARKERS,
    TURN_JSON_CONTRACT,
    build_turn_system_prompt,
)
from app.roles import (
    allowed_role_ids,
    all_role_stats,
    is_allowed_role,
    load_code_exercise_prompt,
    load_interviewer_prompt,
    load_report_prompt_text,
    load_role_prompt,
    load_teacher_prompt,
    load_role_catalog,
    role_label,
)
from app.tools import INTERVIEW_TURN_TOOLS
from app.tools.code_inspect import CODE_INSPECT_TOOL


EXAMPLE_SESSION = {
    "role": "llm-algo",
    "statement": "（本场学生项目陈述）",
    "directions": [
        {
            "id": "d1",
            "title": "项目总览",
            "goal": "讲清做成了哪几块、边界在哪、数据怎么走、训练或检索怎么接",
        }
    ],
    "current_direction_id": "d1",
}


def _tool_public(tool: dict[str, object]) -> dict[str, Any]:
    function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
    return {
        "name": function.get("name"),
        "description": function.get("description"),
        "parameters": function.get("parameters"),
        "schema": tool,
    }


def example_system_prompt(role: str) -> str:
    session = dict(EXAMPLE_SESSION)
    session["role"] = role
    return build_turn_system_prompt(
        session=session,
        turns=[],
        answer="（学生上一答）",
        allow_code_exercise=True,
    )


def build_interviewer_agent_payload(role: str | None = None) -> dict[str, Any]:
    catalog = load_role_catalog()
    selected = role if role and is_allowed_role(role) else allowed_role_ids()[0]
    roles_out: list[dict[str, Any]] = []
    for stats in all_role_stats():
        role_id = stats["id"]
        item = {
            **stats,
            "persona_prompt": load_role_prompt(role_id),
            "system_prompt": example_system_prompt(role_id),
        }
        roles_out.append(item)

    runtime_rules = [
        {
            "id": "min_turns_before_goal_done",
            "value": MIN_TURNS_BEFORE_GOAL_DONE,
            "source": "app/agent.py:MIN_TURNS_BEFORE_GOAL_DONE",
            "text": f"同一方向未满 {MIN_TURNS_BEFORE_GOAL_DONE} 轮，服务端强制 direction_done=false。",
        },
        {
            "id": "min_stuck_before_abandon",
            "value": MIN_STUCK_BEFORE_ABANDON,
            "source": "app/agent.py:MIN_STUCK_BEFORE_ABANDON",
            "text": (
                "学生说不懂时，至少短讲并追问 "
                f"{MIN_STUCK_BEFORE_ABANDON} 次仍空白才允许放弃该方向。"
            ),
        },
        {
            "id": "min_interviewer_before_abandon",
            "value": MIN_INTERVIEWER_BEFORE_ABANDON,
            "source": "app/agent.py:MIN_INTERVIEWER_BEFORE_ABANDON",
            "text": "放弃方向前，该方向上至少要有对应次数的面试官提问。",
        },
        {
            "id": "stuck_markers",
            "value": list(STUCK_MARKERS),
            "source": "app/agent.py:STUCK_MARKERS",
            "text": "命中这些说法视为「不懂」，第一次不得切方向。",
        },
        {
            "id": "first_question_overview",
            "value": "d1 必须是项目总览",
            "source": "app/agent.py:plan_directions",
            "text": "开场 d1 必须是项目总览，第一问禁止跳进公式。",
        },
        {
            "id": "search_library_on_topic",
            "value": True,
            "source": "app/prompts/interviewer.md 与 app/agent.py:run_turn",
            "text": "每轮按当前话题检索面经，条数不固定，没有相关命中就空着。过程句不当检索词。只改写原问。",
        },
        {
            "id": "no_code_coordinates",
            "value": True,
            "source": "app/prompts/interviewer.md",
            "text": "口头提问禁止文件名、路径、行号。",
        },
    ]

    skills = [
        {
            "id": "direction_plan",
            "name": "开场定方向（不看仓库）",
            "source": "app/agent.py:plan_directions",
            "text": (
                "只根据项目陈述 + 该岗位人设/素材结论定 3～5 条方向。"
                "d1 必须是项目总览。开场看不到仓库。"
            ),
        },
        {
            "id": "topic_lock",
            "name": "话题锁",
            "source": "app/agent.py:apply_topic_lock 与 interviewer.md",
            "text": (
                "已定方向是整场宪法。浅答、短答、第一次不懂不得切方向；不懂时可以短讲当前步。"
                f"未满 {MIN_TURNS_BEFORE_GOAL_DONE} 轮或 goal 检查点未覆盖时，"
                "服务端把 direction_done 改回 false。"
            ),
        },
        {
            "id": "tool_policy",
            "name": "按需工具",
            "source": "app/prompts/interviewer.md 与 app/tools/",
            "text": (
                "search_library：每轮按当前话题检索，相关才返回，条数不固定。"
                "code_inspect：核仓库真伪，不把坐标念给学生。"
                "code_exercise：面经里提到的相关手撕才打开编辑器，禁止现场编无关算法题。"
            ),
        },
    ]

    return {
        "decision": catalog.get("decision"),
        "selected_role": selected,
        "roles": roles_out,
        "prompts": {
            "interviewer": load_interviewer_prompt(),
            "role": load_role_prompt(selected),
            "code_exercise": load_code_exercise_prompt(),
            "teacher": load_teacher_prompt(),
            "report": load_report_prompt_text(),
            "turn_contract": TURN_JSON_CONTRACT.replace(
                "{exercise_prompt}", "（此处插入 code_exercise.md + 题库目录）"
            ),
        },
        "system_prompt": example_system_prompt(selected),
        "tools": [_tool_public(item) for item in INTERVIEW_TURN_TOOLS],
        "teacher_tools": [_tool_public(CODE_INSPECT_TOOL)],
        "report_tools": [_tool_public(CODE_INSPECT_TOOL)],
        "skills": skills,
        "runtime_rules": runtime_rules,
        "when_to_call": {
            "search_library": "每轮按当前话题检索；相关 0～10 条；过程句不当检索词。",
            "code_inspect": "学生吹了仓库可能对不上的能力，或需要核对真伪/决定同方向怎么引。",
            "code_exercise": "当前话题属于面经提到的相关手撕，且要核实会不会写；无相关面经则口头问。",
        },
        "role_label": role_label(selected),
    }


def write_static_bundle(path: Path | None = None) -> Path:
    """Bake the Agent page payload so the tab opens without waiting on the API."""

    target = path or STATIC_BUNDLE
    payload = build_interviewer_agent_payload()
    target.write_text(
        "window.INTERVIEWER_AGENT = "
        + json.dumps(payload, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    return target
