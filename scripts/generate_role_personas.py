"""Offline: walk every JD/interview for a role, then ask MiniMax for a persona.

Does not invent library facts. The digest already enumerates all sample ids.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm import complete_json
from app.roles import (
    ROLE_PROMPT_DIR,
    allowed_role_ids,
    extract_role_summary,
    role_label,
    role_one_liner,
)


SYSTEM = """
你是在给「大模型公司技术骨干面试官」写岗位人设。材料全是真实 JD 与面经的结构化摘要。
硬规则：
1. 只根据用户给出的摘要写，禁止编造库里没有的公司标准、题型或术语。
2. 人设必须像这个具体岗位的面试官，不要写成适合所有岗的通用助手。
3. 岗位本质只写这类岗真正在筛什么、常追到哪条边界；每条主张尽量能回指摘要里的高频词或原问。
4. 输出合法 JSON，不要 Markdown。
JSON：
{
  "persona": "200～400 字中文。第二人称不要出现。写清：你是谁、你最在意什么、你怎么追问、你最讨厌什么空话。",
  "essence": "分条中文，每条一行，6～10 条。写筛人标准与考点边界，不要空话。",
  "question_habits": "分条中文，4～6 条，来自面经原问习惯。"
}
""".strip()


def _format_summary(summary: dict) -> str:
    companies = "、".join(f"{name}({count})" for name, count in summary["companies"])
    hot = "、".join(f"{item['term']}×{item['count']}" for item in summary["hot_terms"][:18])
    questions = "\n".join(f"- {item}" for item in summary["questions"][:36])
    excerpts = "\n".join(f"- {item}" for item in summary["jd_excerpts"][:12])
    ids = "、".join(summary["sample_ids"])
    return f"""
岗位：{summary['label']}（{summary['role']}）
覆盖：JD {summary['jd_count']} 条，面经 {summary['interview_count']} 条，合计 {len(summary['sample_ids'])} 条。
公司分布：{companies}
高频词：{hot}

JD 职责摘录：
{excerpts}

面经原问摘录：
{questions}

全部样本 id（证明过完该岗库，不要丢）：
{ids}
""".strip()


def _render_markdown(role: str, summary: dict, generated: dict) -> str:
    label = role_label(role)
    one_liner = role_one_liner(role)
    persona = str(generated.get("persona") or "").strip()
    essence = str(generated.get("essence") or "").strip()
    habits = str(generated.get("question_habits") or "").strip()
    ids = "\n".join(f"- `{item}`" for item in summary["sample_ids"])
    hot = "、".join(f"{item['term']}({item['count']})" for item in summary["hot_terms"][:16])
    companies = "、".join(f"{name}({count})" for name, count in summary["companies"][:12])
    return f"""# {label} · 面试官人设

> {one_liner}
> 本文件由该岗位库内全部真实 JD + 面经归纳，禁止手写空泛人设。
> 覆盖 JD {summary['jd_count']} 条、面经 {summary['interview_count']} 条，合计 {len(summary['sample_ids'])} 条。

## 人设

{persona}

## 岗位本质与考点边界

{essence}

## 真实问法习惯

{habits}

## 库内证据摘要

- 公司分布：{companies}
- 高频词：{hot}

## 覆盖样本 id

{ids}
"""


def generate_one(role: str) -> Path:
    summary = extract_role_summary(role)
    if summary["jd_count"] + summary["interview_count"] < 8:
        raise SystemExit(f"{role} 素材过少，拒绝生成人设")
    raw = complete_json(SYSTEM, _format_summary(summary))
    ROLE_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    path = ROLE_PROMPT_DIR / f"{role}.md"
    path.write_text(_render_markdown(role, summary, raw), encoding="utf-8")
    proof = ROLE_PROMPT_DIR / f"{role}.proof.json"
    proof.write_text(
        json.dumps(
            {
                "role": role,
                "jd_count": summary["jd_count"],
                "interview_count": summary["interview_count"],
                "sample_ids": summary["sample_ids"],
                "hot_terms": summary["hot_terms"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def main() -> None:
    roles = sys.argv[1:] or list(allowed_role_ids())
    for role in roles:
        path = generate_one(role)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
