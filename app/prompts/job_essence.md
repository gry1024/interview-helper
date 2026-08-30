# 岗位本质（已按岗位拆分）

本文件不再注入面试官系统提示。

每个岗位的人设、考点边界、问法习惯，以及「过完该岗全部 JD+面经」的样本 id，写在：

- `app/prompts/roles/llm-algo.md`
- `app/prompts/roles/agent.md`
- `app/prompts/roles/rag.md`

生成方式：`scripts/generate_role_personas.py` 先遍历该岗库内全部样本做结构化摘要，再调用 MiniMax 写成文。
岗位枚举的单一数据源是 `app/jd/roles.json`。
