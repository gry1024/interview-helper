# 代码按需核对 tool 设计文档

> 目标：在不把仓库灌进面试上下文、不把文件名/行号写进下一问的前提下，提供可被面中与报告按需调用的沙箱核对。本步只交付隔离模块与单测，**不接线**第 3 步正在收口的 `main.py` / `agent.py` / `static/`。

## 背景

代码在本产品里只有四件事：核对真伪、决定同方向怎么引、结束评估价值、生成改良建议。仓库全文不进系统提示；提问不引用文件名或行号。

第 2 步已把浅克隆锁在 `repos/{session_id}/`。第 3 步预留了 SSE `tool` 事件契约，但默认不查代码。第 4 步先把 `code_inspect` 做成可独立调用的 tool，再由同事用最小 diff 挂进 turn / 报告。

本模块不读 `app/db.py`，不改 SSE 路由。会话是否可用以文件系统为准：`repos/{session_id}/` 不存在即视为会话不存在或仓库不可用。接线后若 `clone_ok=0`，调用方既可短路，也可仍调用本函数（会得到「仓库不可用」）。

标准样本对照（测试注释与验收用语，不必本步真 clone 公网仓）：

- 陈述含 RoPE / RMSNorm / SwiGLU / Tokenizer / SFT / DPO。
- 回答若吹「rerank / 万卡分布式训练」，tool 应能证伪。
- 下一问仍不得出现 `xxx.py:12`。

## 路径沙箱

根目录必须锁在该场 clone：

```
root = resolve(REPOS_DIR / session_id)
要求：root.parent == resolve(REPOS_DIR) 且 root 是目录
```

`REPOS_DIR` 复用 `app.repository.REPOS_DIR`（运行时读取，便于单测替换）。

拒绝条件（任一即失败，不读目标文件）：

| 输入 | 拒绝 |
| --- | --- |
| `session_id` | 空、控制字符、`/`、`\`、`..`、绝对路径、非 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` |
| `path_hint` | 空以外的绝对路径、`~` 开头、UNC/`//`、盘符 `C:`、任意 `..` 分量、`%` 编码、NUL、控制字符、解析后不在 `root` 下、指向符号链接且真实目标逃出 `root`、落入 `.git` 等跳过目录 |

检索时：

- `os.walk(followlinks=False)`，目录名排序以保证稳定。
- 跳过符号链接（文件与目录）。
- 跳过 `.git`、`node_modules`、`venv`、`.venv`、`__pycache__`。
- 跳过 `>1MB`（可配置）或含 NUL 的疑似二进制文件。

禁止跟随到 `/`、`/etc` 或其他会话目录。模型不能自选 `session_id`：该参数只由服务端注入。

## 接口

路径：`app/tools/code_inspect.py`。面中与报告共用同一函数。

```python
def code_inspect(
    session_id: str,
    query: str,
    path_hint: str | None = None,
    *,
    clone_ok: bool | None = None,
    limits: InspectLimits | None = None,
) -> CodeInspectResult: ...

def run_code_inspect_from_tool_args(
    session_id: str,
    arguments: dict,
    *,
    clone_ok: bool | None = None,
    limits: InspectLimits | None = None,
) -> CodeInspectResult: ...
```

OpenAI 兼容 tool schema（`session_id` **不**出现在 schema 里）：

```json
{
  "type": "function",
  "function": {
    "name": "code_inspect",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string"},
        "path_hint": {"type": "string"}
      },
      "required": ["query"]
    }
  }
}
```

行为：

1. `clone_ok is False` → 直接「仓库不可用」，不扫盘。
2. 校验并锁定 `repos/{session_id}/`。
3. 列顶层名字（截断）。
4. 从 `query` 抽出关键词（拉丁标识 ≥2、连续汉字 ≥2）；按文件名与文件内容检索。`path_hint` 合法时把范围收窄到该文件或子目录。
5. 命中返回相对路径 + 前后各 15 行；总输出 < 6000 字。
6. 超时或触达文件数上限则停止，标记截断，返回已扫到的摘录。

`CodeInspectResult` 字段：

| 字段 | 给谁 | 含义 |
| --- | --- | --- |
| `ok` | 调用方 | 本次核对是否按合约完成（空查询、越狱、会话不存在为 false） |
| `available` | 调用方 | 该场仓库目录是否可用 |
| `error` | 调用方 / 模型 | 短中文错误；不含真实逃逸路径 |
| `conclusion` | 模型 | 哪些主张对得上、哪些对不上 |
| `public_hint` | 思考可见区 / 下一问措辞 | **无文件名、无行号**；只谈能力与证据 |
| `internal_excerpt` | 模型 / `meta_json` | 顶层列表、路径、行号与摘录 |
| `hit_count` / `truncated` / `top_level` | 调用方 | 检索元数据 |

`for_model()`：给模型的短文本（结论 + 内部摘录 + 可公开提示），已截断。  
`for_public()`：只返回 `public_hint`（及不含坐标的结论），供思考区或 SSE `tool.result` 对学生可见的部分。

默认上限（可用环境变量覆盖，不改 `config.py`）：

| 项 | 默认 | 环境变量 |
| --- | --- | --- |
| 超时 | 8s | `INSPECT_TIMEOUT_SEC` |
| 最多读文件数 | 400 | `INSPECT_MAX_FILES` |
| 单文件 | 1MB | `INSPECT_MAX_FILE_BYTES` |
| 输出 | 6000 字 | `INSPECT_MAX_OUTPUT_CHARS` |
| 上下文 | 前后 15 行 | — |
| 最多命中窗 | 8 | — |
| 查询长度 | 500 | — |

## 安全

- [x] 根目录锁在 `repos/{session_id}/`，`..` 与绝对路径一律拒绝。
- [x] `session_id` 由服务端绑定，tool schema 不暴露。
- [x] 不跟随符号链接；不读 `.git` 等跳过树。
- [x] 超时、文件数、单文件体积、输出字数上限。
- [x] 返回摘录/结论，禁止整仓进 prompt。
- [x] `public_hint` 构造时不含路径，并再跑一轮坐标清洗。
- [x] 错误信息不回显尝试读取的 `/etc` 等绝对路径。
- [x] 不读数据库、不改 SSE、不改端口与进程。
- [x] 残余风险：`repos/` 只应由浅 clone 写入；本机硬链接到仓外文件不在 clone 模型内，部署上保持该目录不可被面试用户写入。

## 改动清单

| 文件 | 改动 | 风险 |
| --- | --- | --- |
| `docs/specs/2026-08-30-code-inspect.md` | 本设计 | — |
| `app/tools/__init__.py` | 导出隔离 API | 误被提前 import 进主路径 |
| `app/tools/code_inspect.py` | 沙箱检索 | 路径逃逸、超限、整仓泄漏 |
| `tests/test_code_inspect.py` | 合法读取 / 越狱 / 超限 / 无会话 | 夹具污染真实 `repos/` |

本步明确不改：`app/main.py`、`app/agent.py`、`app/db.py`、`static/`、systemd、端口 80。

## 验收标准

- [x] `path_hint` 含 `..`、绝对路径、符号链接逃逸均拒绝，且不读 `/etc`。
- [x] 不存在的 `session_id` 或缺失 clone 目录 → 会话不存在或仓库不可用。
- [x] 合法读取能对上 RoPE / RMSNorm / SwiGLU / Tokenizer / SFT / DPO。
- [x] 查询 rerank / 万卡 时结论为未体现；`public_hint` 无文件名行号。
- [x] 超体积文件被跳过；文件数/输出上限触发截断。
- [x] `pytest -q tests/test_code_inspect.py` 通过。
- [ ] 面中 SSE 出现 tool 事件、公网 MiniMind 吹 rerank 被证伪——**接线后**才算第 4 步产品完成。本步不算。

## 实现顺序

1. 写本 spec。
2. 实现沙箱解析与检索。
3. 单测：合法、越狱、超限、无会话、标准样本证伪。
4. 只提交上述新文件。

## 反模式

- 不把 clone 全文或大段源码塞进系统提示。
- 不在 `next_question` 或 `public_hint` 里写 `model.py:12`。
- 不让模型传入 `session_id` 或任意绝对路径。
- 不跟随 `..`、符号链接或 `/etc`。
- 不在本步改 `main.py` / `agent.py` / `db.py` / `static/`，不重启 systemd，不改端口。
- 不声称「第 4 步已产品完成」——未接线则只完成隔离能力。
- 不编假仓库冒充 MiniMind 公网验收（本步单测用本地夹具即可）。

## 下一步接线（给第 3 步同事的最小 diff 提纲）

只改调用点，不要重写 tool：

1. **`app/llm.py`**：增加一轮带 `tools` 的 Chat Completions；若 `message.tool_calls`，把 `function.arguments` 交给下面的绑定函数，再把 tool 消息续回模型。最终仍解析现有 turn JSON。
2. **`app/agent.py` `run_turn`**（报告轮同样）：
   - 删掉「本步默认不查代码」。
   - 系统提示改为：仓库不在上下文；要核对就 `code_inspect`；**禁止**把路径行号写入 `next_question`。
   - `session_id=session["id"]` 由服务端传入；`clone_ok=session["clone_ok"]`。
   - `run_code_inspect_from_tool_args(session_id, args, clone_ok=session["clone_ok"])`。
   - 模型续写用 `result.for_model()`；思考可见句用 `result.for_public()`。
   - `meta_json` 记 `[{name, args, result: for_model()}]`。
3. **`app/main.py` SSE**：在思考流前后发已有 `tool` 事件。建议 `data.result` 用 `for_public()`，避免气泡里出现行号；完整摘录只进 `meta_json`。
4. **不要改** `TurnResult.next_question` 的 `CODE_COORDINATE` 校验；它是最后一道闸。
5. **不要改** 本 tool 的根目录规则。

未完成以上接线前，思考区不会出现真实 tool 事件，产品第 4 步未完成。
