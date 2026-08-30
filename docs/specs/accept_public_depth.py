#!/usr/bin/env python3
"""Public Playwright acceptance: two MiniMind sessions, depth + band split.

Not collected by pytest. Run after deploy:

    python3 docs/specs/accept_public_depth.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.report import PRIMARY_BAND_RANK, extract_primary_band  # noqa: E402

PUBLIC_URL = "http://120.26.176.60"
GITHUB_URL = "https://github.com/jingyaogong/minimind.git"
ROLE = "llm-algo"
MIN_ANSWERS = 6
TURN_TIMEOUT_MS = 180_000
START_TIMEOUT_MS = 180_000
END_TIMEOUT_MS = 240_000
CODE_COORDINATE = re.compile(
    r"(?:[\w./-]+\.(?:py|js|ts|tsx|java|go|rs|cpp|c|h))(?::\d+)?",
    re.I,
)
MIND_STATEMENT = (
    "MiniMind:全链路轻量级大语言模型复现与训练：为深入探究LLM内部机制，"
    "复现了一个类LLaMA架构的轻量级语言模型 (Decoder-only)，涵盖从 Tokenizer训练、"
    "预训练(Pre-train)、指令微调(SFT)到DPO对齐的完整流水线。核心工作: "
    "基于PyTorch复现了LLaMA的核心组件，包括RoPE旋转位置编码（提升外推性) "
    "RMSNorm(优化收敛速度)及SwiGLU激活函数， 深入掌握了 Transformer的底层计算细节。"
    "构建并清洗中文指令数据集，设计 Prompt Template，成功跑通了从无监督预训练到"
    "指令跟随的完整训练闭环。"
)
EXCELLENT_ANSWERS = [
    "token ID 先是词表里的整数下标，会去查 embedding 表，得到 hidden state，形状从 [B, T] 变成 [B, T, n_embd]。这一步在 RoPE 之前，不是直接做位置编码。",
    "RoPE 不是把位置向量加到 hidden 上，而是对 Q 和 K 按二维子空间用 cos/sin 做旋转，相对角度能保住，所以外推比绝对位置加法更稳。我没改成 ALiBi。",
    "RMSNorm 不做均值中心化，只除以 RMS 再乘可学习的 gamma，比 LayerNorm 少一个减均值，收敛更稳。我承认没做完整的对照表。",
    "SwiGLU 是门控：silu(xW_gate) 乘上 xW_up，再经 W_down，不是普通 ReLU/GELU。我按 LLaMA 这条线复现，没有另做 MoE。",
    "Tokenizer 是在中文语料上训的分词器，预训练做 next-token。这是小模型复现，不是分布式万卡训练，我也没做检索 rerank。",
    "SFT 用指令模板，损失主要打在回答 token 上；DPO 用偏好对、对照参考策略。边界是：没有 PPO/GRPO，也没有 rerank 或万卡集群。",
]
WEAK_ANSWERS = [
    "用了 RoPE 提升外推，公式我一下子写不出来。",
    "这块我不太懂。",
    "不太清楚，大概就是普通 Transformer 那样吧。",
    "对了，这个项目我还做了 rerank，并且在分布式万卡上做过大规模训练。",
    "你说的那个我还是不太懂。",
    "就是按论文做的，细节我没怎么看。",
]
EVIDENCE_PATH = Path(__file__).with_name("accept_public_depth_last.json")


def log(message: str) -> None:
    print(message, flush=True)


def wait_ready(page) -> None:
    page.wait_for_selector("#send-answer:not([disabled])", timeout=TURN_TIMEOUT_MS)
    page.wait_for_selector("#end-interview:not([disabled])", timeout=TURN_TIMEOUT_MS)


def start_session(page) -> str:
    last_error = "开始面试失败"
    for attempt in range(1, 4):
        page.goto(PUBLIC_URL, wait_until="domcontentloaded", timeout=60_000)
        page.click("#tab-interview")
        page.wait_for_selector("#session-form", timeout=30_000)
        page.fill("#github-url", GITHUB_URL)
        page.fill("#statement", MIND_STATEMENT)
        page.select_option("#role", ROLE)
        page.click("#start-session")
        try:
            page.wait_for_selector(
                "#interview-live:not([hidden])",
                timeout=START_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            status = ""
            if page.locator("#session-status").count():
                status = page.locator("#session-status").inner_text()
            last_error = f"第 {attempt} 次开场超时：{status or '无错误文案'}"
            log(last_error)
            time.sleep(8)
            continue
        page.wait_for_selector("#chat-log .bubble", timeout=START_TIMEOUT_MS)
        wait_ready(page)
        session_id = page.locator("#interview-live").get_attribute("data-session-id")
        if not session_id:
            last_error = "开始面试后没有拿到 session id"
            continue
        return session_id
    raise AssertionError(last_error)


def answer_once(page, text: str, index: int) -> dict[str, str]:
    wait_ready(page)
    before_thoughts = page.locator(".thought").count()
    before_questions = page.locator(".bubble-row.interviewer .bubble").count()
    page.fill("#answer-input", text)
    page.click("#send-answer")
    page.wait_for_function(
        "n => document.querySelectorAll('.thought').length >= n",
        arg=before_thoughts + 1,
        timeout=TURN_TIMEOUT_MS,
    )
    wait_ready(page)
    page.wait_for_function(
        "n => document.querySelectorAll('.bubble-row.interviewer .bubble').length >= n",
        arg=before_questions + 1,
        timeout=TURN_TIMEOUT_MS,
    )
    thought = page.locator(".thought").nth(-1).inner_text()
    question = page.locator(".bubble-row.interviewer .bubble").nth(-1).inner_text()
    log(f"  第 {index} 轮思考摘要：{thought[:120].replace(chr(10), ' / ')}")
    log(f"  第 {index} 轮下一问：{question[:80]}")
    return {"thought": thought, "question": question, "answer": text}


def end_session(page) -> str:
    wait_ready(page)
    page.click("#end-interview")
    page.wait_for_selector(".report-article-body, .report-stream", timeout=END_TIMEOUT_MS)
    page.wait_for_function(
        """() => {
            const body = document.querySelector('.report-article-body');
            const stream = document.querySelector('.report-stream');
            const text = (body && body.innerText) || (stream && stream.innerText) || '';
            return text.includes('整场主档') || text.includes('总评');
        }""",
        timeout=END_TIMEOUT_MS,
    )
    time.sleep(2)
    if page.locator(".report-article-body").count():
        return page.locator(".report-article-body").inner_text()
    return page.locator(".report-stream").inner_text()


def fetch_review(page, session_id: str) -> dict:
    response = page.request.get(f"{PUBLIC_URL}/api/reviews/{session_id}")
    if not response.ok:
        raise AssertionError(f"复盘 {session_id} 读取失败：{response.status}")
    return response.json()


def run_persona(page, name: str, answers: list[str]) -> dict:
    log(f"\n=== 开始场次：{name} ===")
    session_id = start_session(page)
    log(f"session_id={session_id}")
    turns = []
    for index, answer in enumerate(answers, start=1):
        log(f"{name} 发送第 {index} 轮")
        turns.append(answer_once(page, answer, index))
    if len(turns) < MIN_ANSWERS:
        raise AssertionError(f"{name} 只答了 {len(turns)} 轮，不能结束")
    visible = end_session(page)
    snapshot = fetch_review(page, session_id)
    report_text = snapshot.get("report", {}).get("text") or ""
    band = extract_primary_band(report_text)
    user_turns = [item for item in snapshot.get("turns", []) if item.get("role") == "user"]
    thoughts = [item for item in snapshot.get("turns", []) if item.get("role") == "thought"]
    log(f"{name} 结束：用户轮次={len(user_turns)} 主档={band}")
    return {
        "name": name,
        "session_id": session_id,
        "user_turns": len(user_turns),
        "band": band,
        "report_text": report_text,
        "visible_report": visible,
        "live_turns": turns,
        "thoughts": [item.get("body") or "" for item in thoughts],
        "next_questions": [
            item.get("body") or ""
            for item in snapshot.get("turns", [])
            if item.get("role") == "interviewer"
        ],
    }


def assert_weak_inspect(result: dict) -> None:
    blob = "\n".join(result["thoughts"] + [item["thought"] for item in result["live_turns"]])
    if "查代码：是" not in blob:
        raise AssertionError("较差场没有出现「查代码：是」")
    if not re.search(r"未体现|仓库未体现", blob):
        raise AssertionError("较差场查代码结论没有证伪 rerank/万卡")
    if not re.search(r"rerank|万卡", blob, re.I):
        raise AssertionError("较差场查代码结论没有点到 rerank/万卡")
    after_claim = False
    for turn in result["live_turns"]:
        if "rerank" in turn["answer"] and "万卡" in turn["answer"]:
            after_claim = True
            continue
        if after_claim and CODE_COORDINATE.search(turn["question"]):
            raise AssertionError(f"证伪后的下一问暴露了文件名或行号：{turn['question']}")


def assert_reviews_list(page, excellent_id: str, weak_id: str) -> None:
    page.goto(PUBLIC_URL, wait_until="domcontentloaded", timeout=60_000)
    page.click("#tab-reviews")
    page.wait_for_selector(".list-item", timeout=30_000)
    listing = page.request.get(f"{PUBLIC_URL}/api/reviews").json()
    ids = {item.get("id") for item in listing}
    if excellent_id not in ids or weak_id not in ids:
        raise AssertionError(f"复盘列表缺少场次：{ids}")
    labels = page.locator(".list-item").all_inner_texts()
    if len(labels) < 2:
        raise AssertionError("复盘页可见条目不足两场")


def main() -> int:
    evidence: dict = {"ok": False, "error": None}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(TURN_TIMEOUT_MS)
            excellent = run_persona(page, "优秀", EXCELLENT_ANSWERS)
            weak = run_persona(page, "一般较差", WEAK_ANSWERS)
            assert_weak_inspect(weak)
            if excellent["user_turns"] < MIN_ANSWERS or weak["user_turns"] < MIN_ANSWERS:
                raise AssertionError("存在未满 6 轮就结束的场次")
            if PRIMARY_BAND_RANK[excellent["band"]] <= PRIMARY_BAND_RANK[weak["band"]]:
                raise AssertionError(
                    f"档位没有拉开：优秀={excellent['band']} 较差={weak['band']}"
                )
            assert_reviews_list(page, excellent["session_id"], weak["session_id"])
            browser.close()
        evidence = {
            "ok": True,
            "excellent": {
                "session_id": excellent["session_id"],
                "user_turns": excellent["user_turns"],
                "band": excellent["band"],
                "report_excerpt": excellent["report_text"][:800],
            },
            "weak": {
                "session_id": weak["session_id"],
                "user_turns": weak["user_turns"],
                "band": weak["band"],
                "inspected": True,
                "report_excerpt": weak["report_text"][:800],
            },
        }
        EVIDENCE_PATH.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log("\n验收通过。")
        log(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0
    except PlaywrightTimeout as exc:
        evidence["error"] = f"timeout: {exc}"
    except Exception as exc:  # noqa: BLE001 - write evidence then fail
        evidence["error"] = str(exc)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"验收失败：{evidence['error']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
