#!/usr/bin/env python3
"""Public Playwright acceptance: two MiniMind sessions, depth + band split.

Not collected by pytest. Run after deploy:

    python3 docs/specs/accept_public_depth.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.demo_catalog import get_demo  # noqa: E402
from app.report import PRIMARY_BAND_RANK, extract_primary_band  # noqa: E402

PUBLIC_URL = "http://120.26.176.60"
MINIMIND = get_demo("minimind")
NANO_VLLM = get_demo("nano-vllm")
GITHUB_URL = MINIMIND["github_url"]
ROLE = MINIMIND["role"]
MIND_STATEMENT = MINIMIND["statement"]
NANO_VLLM_GITHUB_URL = NANO_VLLM["github_url"]
NANO_VLLM_STATEMENT = NANO_VLLM["statement"]
MIN_ANSWERS = 14
TURN_TIMEOUT_MS = 300_000
START_TIMEOUT_MS = 180_000
END_TIMEOUT_MS = 300_000
CODE_COORDINATE = re.compile(
    r"(?:[\w./-]+\.(?:py|js|ts|tsx|java|go|rs|cpp|c|h))(?::\d+)?",
    re.I,
)
EXCELLENT_CATALOG = [
    (
        ("哪几块", "做成", "介绍", "项目", "主干", "框架", "流水线"),
        "这个项目我做成四块。第一块是自己训的 Tokenizer，把中文语料切成 token。第二块是 Decoder-only 的类 LLaMA 结构：embedding 查表、RoPE 旋 Q/K、RMSNorm、SwiGLU，最后用 weight tying 出 logits。第三块是预训练，做 next-token。第四块是 SFT 加 DPO：指令模板只在回答 token 上算损失，再用偏好对做对齐。我没做 RAG、rerank，也没有万卡分布式，就是单机把闭环跑通。",
    ),
    (
        ("embedding", "token id", "hidden", "查表", "整数", "下标", "词表"),
        "一个 token ID 就是词表里的整数下标。模型先拿它去查 embedding 表，得到一条 hidden 向量，形状从 [B, T] 变成 [B, T, n_embd]。这一步只做离散到连续的查找，还没有乘位置向量。位置是后面 RoPE 在 Q、K 上旋进去的。如果词表和 embedding 行数对不上，这里会直接错位，所以 Tokenizer 训完要和这张表对齐。",
    ),
    (
        ("rope", "旋转", "位置编码", "外推", "cos", "sin"),
        "位置编码我用的是 RoPE，不是把绝对位置向量加到 hidden 上。做法是把 Q、K 按偶数维两两一组，用该位置的 cos、sin 做二维旋转，相对位置差会进点积。这样外推比可学习绝对位置稳一些。我旋的是 Q 和 K，不旋 V。MiniMind 这条线和 LLaMA 一样，我没改成 ALiBi，也没有另做长度插值实验，这是明确边界。",
    ),
    (
        ("rms", "norm", "归一", "均值"),
        "归一化我用 RMSNorm：不算通道均值，只算均方根，hidden 除以 RMS 再乘可学习的 gamma。比 LayerNorm 少一次减均值，实现更短，也是 LLaMA 系常见选择。我把它放在注意力和 FFN 前面。我承认没有在同一套数据上把 LayerNorm 和 RMSNorm 做成完整对照表，结论主要来自复现和训练是否收敛。",
    ),
    (
        ("swiglu", "激活", "门控", "relu", "gelu", "ffn"),
        "FFN 不是一层 ReLU/GELU，而是 SwiGLU：一路 SiLU(xW_gate) 做门，一路 xW_up，两者按元素相乘，再经 W_down 投回去。门控能压掉一部分通道，比固定激活更灵活。这是跟着 LLaMA 复现的，没有上 MoE。参数量会比单层 FFN 多一截，小模型上我用缩小隐层来换。",
    ),
    (
        ("attention", "qkv", "头", "缩放", "softmax", "因果", "mask"),
        "注意力是因果自注意力。hidden 先投成 Q、K、V，按头切开；score 是 QK^T 除以根号 d_k，再加下三角 mask，softmax 后乘 V，最后拼回去做输出投影。除根号 d_k 是怕点积随维度变大、softmax 变尖。训练时整段并行，推理才靠 KV cache 逐步追加。我没做 GQA，就是常规 MHA。",
    ),
    (
        ("tokenizer", "分词", "bpe", "语料"),
        "Tokenizer 是我在中文语料上自己训的，不是直接拿一个英文 BPE 硬套。预训练目标就是 next-token，所以词表覆盖和切分粒度会直接进损失。指令阶段会套 Prompt 模板，但分词器本身没换。脏数据、超长样本会在进训之前截断或丢掉。我没有做 byte-level 回退的完整评测，这是缺口。",
    ),
    (
        ("sft", "指令", "模板", "微调"),
        "SFT 我用中文指令数据，套固定模板，损失主要打在回答 token 上，提示部分 mask 掉，避免模型只会复读指令。数据是自己清洗过的，不是把网上问答原样倒进去。这一步只解决「听得懂指令」，不解决偏好对齐。我没做多轮对话的复杂系统提示，模板比较短，这是有意收的范围。",
    ),
    (
        ("dpo", "对齐", "偏好", "参考"),
        "对齐我走 DPO，不用 PPO。一对偏好样本里，chosen 相对 rejected 提高对数几率，同时用参考策略约束别跑太远。这样不用另训 reward model，也不用在线采样。边界很清楚：没有 KL 系数扫、没有 GRPO，也没有人类实时标注。数据量小，我只验证指令是否更听，不宣称通用对齐。",
    ),
    (
        ("预训练", "pretrain", "损失", "next"),
        "预训练就是标准的因果语言建模：当前 token 预测下一个，损失是词表上的交叉熵。数据是清洗后的中文文本，和后面 SFT 的指令数据分开。小模型上我先把这条损失压稳，再接到指令微调，没有在预训练里混大量对话。也没有做 MoE 或超长上下文扩展。",
    ),
    (
        ("共享", "复用", "转置", "logits", "tying", "输出层", "同一张"),
        "输出层我做了 weight tying：LM head 和 embedding 共用一张词表矩阵的转置，hidden 映到 logits 时不再另训一套 vocab×hidden。参数少，输入输出空间也更齐。代价是改 embedding 会牵动输出，两边一起动。我没有独立训输出头，也没有在 tying 和独立头之间做对照。",
    ),
]
EXCELLENT_FALLBACK = (
    "我还是贴着 MiniMind 自己的对象讲。结构上是 Decoder-only：embedding 查表、"
    "RoPE 只旋 Q/K、层内 RMSNorm 加 SwiGLU，输出和 embedding 做 weight tying。"
    "训练闭环是 Tokenizer 之后预训练 next-token，再 SFT 只打回答 token，最后 DPO 用偏好对。"
    "我明确没做检索、rerank 和万卡集群，这些不在仓库里，也不该拿来充项目。"
)
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
    dismiss_code_ide(page)
    page.wait_for_selector("#send-answer:not([disabled])", timeout=TURN_TIMEOUT_MS)


def dismiss_code_ide(page) -> None:
    collapse = page.locator("#code-ide-collapse")
    try:
        if collapse.count() and collapse.first.is_visible():
            collapse.first.click(timeout=3_000)
    except Exception:
        pass
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


def last_question(page) -> str:
    return page.locator(".bubble-row.interviewer .bubble").nth(-1).inner_text()


def pick_excellent_answer(question: str, used: list[str]) -> str:
    lowered = question.lower()
    for keys, answer in EXCELLENT_CATALOG:
        if answer in used:
            continue
        if any(key.lower() in lowered for key in keys):
            return answer
    for _keys, answer in EXCELLENT_CATALOG:
        if answer not in used:
            return answer
    return EXCELLENT_FALLBACK


def clone_failed(page) -> bool:
    notice = page.locator("#clone-notice")
    if notice.count() == 0:
        return False
    try:
        hidden = notice.get_attribute("hidden")
        if hidden is not None:
            return False
        text = notice.inner_text().strip()
        return "不可用" in text or "失败" in text
    except Exception:
        return False


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
        if clone_failed(page):
            last_error = f"第 {attempt} 次开场 clone 失败，session={session_id}"
            log(last_error)
            time.sleep(8)
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
    last_error = "复盘读取失败"
    for attempt in range(1, 8):
        try:
            response = page.request.get(f"{PUBLIC_URL}/api/reviews/{session_id}")
        except Exception as exc:  # noqa: BLE001 - retry across deploys
            last_error = f"复盘 {session_id} 第 {attempt} 次连接失败：{exc}"
            log(last_error)
            time.sleep(4)
            continue
        if response.ok:
            return response.json()
        last_error = f"复盘 {session_id} 读取失败：{response.status}"
        log(last_error)
        time.sleep(4)
    raise AssertionError(last_error)


def load_existing_session(page, session_id: str, name: str) -> dict:
    snapshot = fetch_review(page, session_id)
    report_text = snapshot.get("report", {}).get("text") or ""
    band = extract_primary_band(report_text)
    user_turns = [item for item in snapshot.get("turns", []) if item.get("role") == "user"]
    thoughts = [item for item in snapshot.get("turns", []) if item.get("role") == "thought"]
    log(f"复用已结束场次 {name} session_id={session_id} 轮次={len(user_turns)} 主档={band}")
    return {
        "name": name,
        "session_id": session_id,
        "user_turns": len(user_turns),
        "band": band,
        "report_text": report_text,
        "visible_report": report_text,
        "live_turns": [],
        "thoughts": [item.get("body") or "" for item in thoughts],
        "next_questions": [
            item.get("body") or ""
            for item in snapshot.get("turns", [])
            if item.get("role") == "interviewer"
        ],
    }


def run_persona(page, name: str, answers: list[str] | None) -> dict:
    log(f"\n=== 开始场次：{name} ===")
    session_id = start_session(page)
    log(f"session_id={session_id}")
    turns = []
    used_excellent: list[str] = []
    planned = answers or [""] * MIN_ANSWERS
    for index, preset in enumerate(planned, start=1):
        if name.startswith("优秀"):
            answer = pick_excellent_answer(last_question(page), used_excellent)
            used_excellent.append(answer)
        else:
            answer = preset
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
    log(f"验收开始 resume={os.getenv('RESUME_EXCELLENT_ID', '')}")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            for _wait in range(10):
                try:
                    if page.request.get(f"{PUBLIC_URL}/api/health").ok:
                        break
                except Exception:
                    time.sleep(3)
            page.set_default_timeout(TURN_TIMEOUT_MS)
            resume_excellent = os.getenv("RESUME_EXCELLENT_ID", "").strip()
            if resume_excellent:
                excellent = load_existing_session(page, resume_excellent, "优秀")
            else:
                excellent = run_persona(page, "优秀", None)
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
