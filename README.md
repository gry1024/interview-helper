# Interview Helper

把简历上的项目，变成你真正拥有的项目。

这不是把材料丢给 ChatGPT。左侧三个入口构成一条闭环：

1. **模拟面试**：提交 GitHub 仓库、项目陈述和岗位类别。开场先定 3～5 条方向并锁住话题，再逐步深挖。思考挂在该答下方；代码只在起疑时按需核对，不把仓库全文塞进 prompt。
2. **面试复盘**：结束后左对话、右报告，原文回放，刷新后列表仍在。
3. **JD 库**：只展示有可核验来源的真实 JD 与面经，用来归纳岗位本质，不存在现场爬取或编造。

刻意不做：登录、八股、LeetCode、语音、多项目、现场爬 JD、把仓库全文塞进模型上下文。

## 本地运行

1. 复制环境变量模板（**不要提交 `.env`，也不要把真实密钥写进文档**）：

   ```bash
   cp .env.example .env
   ```

2. 按 `.env.example` 里的变量名自行填写 MiniMax 兼容接口配置，以及本机监听地址。仓库只提供变量名，不提供任何真实值。

3. 安装依赖并启动：

   ```bash
   python3 -m pip install -r requirements.txt
   python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

4. 浏览器打开本机地址，走三入口：开始面试 → 回答至少一轮 → 结束看报告 → 复盘回放 → 查看 JD 库来源。

生产环境可用 systemd 托管同一条 `uvicorn` 进程；不要另起第二个抢端口的服务。

## 如何测

```bash
pytest -q
```

单测覆盖 GitHub URL 白名单、clone 路径锁定、snapshot 原文往返等契约。它们不能代替浏览器实操：需要在真实页面上点三入口、提交标准样本、看思考是否贴在该回答下、结束报告是否只出现在右侧。

标准样本（全程用这一份）：

- 岗位：`llm-algo`（LLM 算法实习）
- 仓库：`https://github.com/jingyaogong/minimind.git`
- 陈述：项目文档里的 MiniMind 原文（Tokenizer / 预训练 / SFT / DPO，以及 RoPE / RMSNorm / SwiGLU）

非法仓库另开一场，例如 GitLab 链接，应看到「只允许 https://github.com 仓库链接」。

## 配置

见 [`.env.example`](.env.example)。需要的是 MiniMax 兼容 Chat Completions 的密钥、`base_url`、模型名，以及 clone 超时/体积上限。密钥、服务器密码、个人访问令牌都不要写进本仓库。
