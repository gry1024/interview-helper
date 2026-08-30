# 手撕代码编辑器：后端 tool 与提交契约

> 目标：聊到面经常考的实现（如 Transformer → Multi-Head Attention）时，面试官 Agent 调用 `code_exercise`，前端弹出 Python 编辑器；学生边写边仍可对话；提交后按代码文本评价并继续追问。不是 LeetCode，不做执行沙箱。

## 背景

`code_inspect` 只核对仓库真伪，不能核实「会不会写」。本步在已有 tool loop 上并列增加 `code_exercise`：题只从面经归纳的题库取，禁止模型现场编无来源题。前端同事只改 `static/`（Monaco）；本步不改静态资源。

## 题库

路径：`app/jd/code_exercises.json`。每题字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定 id，如 `mha-forward` |
| `title` | 展示标题 |
| `prompt` | 题面（贴机制，不考无关算法） |
| `language` | 固定 `python` |
| `starter` | 不完整 starter |
| `source_ids` | `interviews.json` / `jds.json` 中的样本 id |
| `topics` | 匹配关键词（attention、rope、lora…） |
| `roles` | 适用岗位：`llm-algo` / `training` / `rag` |

模型调用时带 `exercise_id`（优先）或 `topic`。服务端解析题库，匹配失败则返回错误，**不**用模型生成的 prompt/starter。

调用时机（`interviewer.md` 追加小节 + `code_exercise.md`）：

- 当前方向需要核实「会不会写」，且该实现属于面经常考手撕。
- 同一场同一题不重复。
- 一轮最多打开一题。
- 禁止链表、排序、背包等无关题。
- 学生刚提交代码的评价轮不再打开新题。

## SSE

可与现有 `event: tool` 并存。前端认专用事件：

```
event: code_exercise
data: {
  "exercise_id": "mha-forward",
  "title": "手撕 Multi-Head Attention",
  "prompt": "用 Python 实现……",
  "language": "python",
  "starter": "class MultiHeadAttention:\n    def __init__(self, d_model, n_heads):\n        "
}
```

时机：本轮 `run_turn` 成功打开一题之后、`thought_delta` 之前。编辑器打开**不**锁会话；`POST /api/sessions/{id}/turns` 仍可用。

同时仍发一条 `event: tool`，`name=code_exercise`，`result` 为学生可见短句（无题面全文亦可，题面以专用事件为准）。

## 提交

```
POST /api/sessions/{id}/code-submissions
{ "exercise_id": "mha-forward", "code": "..." }
```

- 写限流、会话须 `ready`/`live`、同一场同时只一轮（复用 `_active_turns`）。
- 题必须在题库中，否则 400。
- 落库：一条 `user`，`body` 为代码原文，`meta_json` 为 `{"kind":"code_submission","exercise_id":"..."}`。
- 随后走现有 `run_turn`（`allow_code_exercise=false`），SSE 仍是 `thought_delta` → `question` → `done`。
- 提交后 `status` 仍为 `live`。
- v1 不编译、不跑沙箱；面试官只根据代码文本评价。

选「提交即 `run_turn`」而不是「只存代码、等下一句 turns」：一次请求就能给出思考+下一问，改动面更小。

## 接线（加法）

1. `app/llm.py`：现有 tool loop 已按 `tool_calls` 分发，不必拆循环；`run_turn` 把 `CODE_EXERCISE_TOOL` 与 `CODE_INSPECT_TOOL` 并列传入。
2. `app/agent.py`：只加 tool 分发与题库目录注入，不改话题锁 / 报告定档。
3. `app/db.py`：`append_turn_bundle` 增加可选 `user_meta`，默认 `None`（用户行 `meta_json` 仍为空）。
4. `app/main.py`：SSE 发 `code_exercise`；新增提交路由。
5. 不改 `static/`、不改话题锁阈值、不覆盖 `interviewer.md` 深度规则。

## 验收

- 题库 8～15 道，每题有真实 `source_ids`。
- 模型编造的 `exercise_id` / 无匹配 `topic` → 不弹编辑器。
- 同场重复 id、同轮第二题 → 拒绝。
- 打开编辑器后 `POST .../turns` 仍 2xx。
- 提交 2xx，SSE 含思考与下一问，会话仍 `live`。
- `pytest -q` 全绿；不提交 `.env` / `AGENT.md`。
