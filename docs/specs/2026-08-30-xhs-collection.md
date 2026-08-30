# 2026-08-30 样本库采集说明

## 目标

扩充本科生可投的 LLM / 训练对齐 / RAG·Agent 实习 JD 与面经。每条必须有可打开的 `source_url`，摘录原文，不编造。

## 小红书爬虫

指定工具：<https://github.com/cv-cat/Spider_XHS.git>

尝试结果：**未跑通，没有写入任何“爬到的小红书笔记”。**

阻塞：

1. **本机没有小红书登录 Cookie。** 已只读检查项目 `.env`、环境变量、`VibeCoding-Scaffold/重要信息.txt` 与常见本地路径，均无 `COOKIES` / 小红书会话。README 要求在工具根目录 `.env` 写 `COOKIES='...'`，且必须是登录后 Cookie。
2. **仓库克隆失败。** `git clone` 两次均报 `RPC failed; curl 16 Error in the HTTP2 framing layer`。`master.zip` 直连超时；镜像要么证书过期，要么下到的不是合法 zip。
3. **官网与笔记页是前端渲染。** `job.xiaohongshu.com/campus/position/*` 与 `www.xiaohongshu.com/explore` 用 curl 只能拿到 SPA 壳。本环境 browser MCP 无法稳定建 tab，因此没有把搜索引擎摘要里的小红书校园 JD 写进主库（避免“没打开页面却当已核验”）。

工具用法（供后续有 Cookie 时）：`pc_api.search_some_note(query, require_num, cookies_str, ...)`。Cookie 只从环境变量或仓库外本地文件读取，**不要写入 git**。若把工具放进本仓，目录必须是已 gitignore 的 `tools/Spider_XHS/`。

建议关键词：`大模型算法实习 面经`、`LLM 实习 JD`、`字节 大模型 实习`、`RAG Agent 实习 面经`、`训练 对齐 实习`。多关键词去重，按 `source_url` 合并。

## 实际采用的公开来源

在爬虫不可用的前提下，只收录本次成功打开并读到正文的页面：

- 官方招聘：字节海外职位页、百度校园、美团校园职位详情
- 牛客职位 / 面经 / 讨论帖（职位正文或面经题单）

学历规则：正文或职位页明确仅硕博 / PhD 的不进 `jds.json` / `interviews.json`，写入 `app/jd/_filtered_out.json` 备查。本科、本科及以上、学历不限且正文未写仅研究生的保留。

## 不要做的事

- 不要把 Cookie、token、`.env`、`AGENT.md`、`重要信息.txt` 提交进 git
- 不要重启占用 80 端口的线上服务来完成本次采集
- 不要为了凑数改写或补造帖子内容
