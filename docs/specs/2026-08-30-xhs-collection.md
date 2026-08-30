# 2026-08-30 小红书采集说明

## 结果

用 Spider_XHS 的 **cookie 模式**（`COOKIES` 环境变量或仓库外 `/root/.xhs_cookies`）登录后持续搜索。未使用手机号验证码。

- 登录：`user/me` 确认非游客、有 `user_id`
- 采集脚本在仓库外 `/root/xhs_harvest/`（进度 `progress.json`、原始详情 `raw/`）
- 关键词约 150 个，每词最多 4 页；按 `source_url` 去重后增量写入 JSON
- `text` 为笔记标题+正文摘录，不改写成摘要；打不开详情或无正文的不入库
- 求职日记、碎碎念、前端岗、法律 LLM、纯广告、图里才有题的短帖会丢掉
- 明确仅硕博的进 `app/jd/_filtered_out.json`
- Cookie、手机号未写入仓库、JSON、文档或 commit

## 关键词（持续扩）

公司 ×（大模型/LLM/算法实习/Agent/RAG）×（面经/一面/二面/日常实习/暑期），外加：

- 手撕 attention、RoPE 面经、LoRA 实习面经、KV cache 面经
- GRPO/SFT/RLHF/DPO/FlashAttention/MoE/vLLM 实习面经
- 字节/阿里/淘天/腾讯/美团/百度/快手/小红书/蚂蚁/网易/拼多多/华为/商汤/智谱/月之暗面/MiniMax/阶跃/零一万物 等

进度文件记录已跑完的词和下一批评列；**不要把「库已经够了」当成停搜理由**。

## 入库

- `source_name=小红书`，`source_url` 为 `https://www.xiaohongshu.com/explore/{note_id}`
- 按 `source_url` 去重
- 扩展字段：`published_at`、`education`、`requirements`、`question_types`、`experience`
- 本科可投留在主库；仅硕士/博士进过滤库

## 不要做的事

- 不要把 Cookie 或手机号提交进 git
- 不要重启占用 80 端口的服务
- 不要编造未打开或未读到正文的笔记
