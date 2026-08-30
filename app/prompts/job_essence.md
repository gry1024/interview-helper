# LLM 算法实习岗位本质与面试官前置知识

> 本文件仅由 `app/jd/jds.json` 与 `app/jd/interviews.json` 的真实来源归纳。
> 括号内 id 是每条主张的证据索引；样本扩充后必须同步复核本文件。

## 通用筛人标准

1. **不只会复述架构，还能沿数据流解释机制与取舍。** 候选人应能从输入、表示、注意力到输出解释 Transformer，并说明具体优化解决了什么瓶颈，而不是只背定义。（`pdd-large-model-algorithm-intern-2027`、`bytedance-llm-algorithm-intern-interview`、`bytedance-llm-daily-intern-interview`、`ctrip-large-model-intern-interview`）
2. **真正跑过训练闭环。** 重点核对数据处理、Pre-training、SFT、Post-training/RL、评估与迭代是否形成闭环，以及每一步如何证明有效。（`bytedance-data-model-intern-2026`、`bytedance-llm-posttraining-rl-intern-2026`、`xiaohongshu-llm-post-training-intern-2026`、`pdd-large-model-algorithm-intern-2027`）
3. **数据不是背景材料，而是算法结果的一部分。** 要能说清数据来源、清洗、结构、合成、过滤、有效性验证与多样性控制，并解释数据决策如何影响模型行为。（`bytedance-data-model-intern-2026`、`xiaohongshu-llm-post-training-intern-2026`、`tencent-llm-algorithm-second-interview`）
4. **方法选择必须有可验证理由。** 对 LoRA/QLoRA、PPO/GRPO/DPO、量化、推理框架等选择，要能交代约束、替代方案、稳定性或资源代价和评估证据。（`xiaohongshu-llm-post-training-intern-2026`、`bytedance-llm-algorithm-intern-interview`、`bytedance-llm-daily-intern-interview`、`alibaba-taotian-llm-intern-interview`、`tencent-llm-algorithm-second-interview`）
5. **工程能力要落到资源与上线约束。** 除算法效果外，还要理解显存、延迟、吞吐、上下文长度、分布式训练和推理服务之间的权衡。（`xiaohongshu-llm-post-training-intern-2026`、`bytedance-llm-daily-intern-interview`、`tencent-llm-algorithm-second-interview`）
6. **Agent / RAG 项目要能说清闭环与失败处理。** 包括检索链路、工具调用调度、评估维度、异常 fallback 与 memory 设计。（`bytedance-ai-native-rag-db-intern-2027`、`baidu-agent-algorithm-intern-j97505`、`alibaba-taotian-llm-intern-interview`）

## 按岗位方向加载

### `llm-algo`：基座与通用大模型算法

- 核心链路：Transformer 组件与数据流 → 预训练/微调/对齐 → 评估可信度 → 推理或业务落地。
- 深挖重点：组件为什么这样设计、训练阶段如何衔接、失败现象如何定位、改动是否有对照实验。
- 证据：`pdd-large-model-algorithm-intern-2027`、`bytedance-data-model-intern-2026`、`bytedance-seed-llm-research-intern-2027`、`ctrip-large-model-intern-interview`、`meituan-llm-intern-interview`。

### `training`：训练、后训练与对齐

- 核心链路：数据构造与过滤 → SFT → Reward/偏好信号 → PPO/GRPO/DPO 等 RL → 稳定性与效果评估。
- 深挖重点：奖励是否真的衡量正确性、如何防止 reward hacking、算法选择依据、分布式资源约束。
- 证据：`xiaohongshu-llm-post-training-intern-2026`、`bytedance-llm-posttraining-rl-intern-2026`、`bytedance-data-model-intern-2026`、`tencent-llm-algorithm-second-interview`、`alibaba-taotian-llm-intern-interview`。

### `rag`：检索增强与 Agent 应用

- 核心链路：语料清洗 → chunk → embedding/召回 → rerank → 生成 → 线上评估。
- 深挖重点：切分策略为什么适合数据、召回率如何测、Embedding 与 Rerank 各自承担什么、上线后瓶颈在哪里。
- Agent 项目还应核对任务拆解、工具调用、闭环执行、fallback 和长链路失败处理。
- 证据：`bytedance-llm-algorithm-intern-interview`、`bytedance-ai-native-rag-db-intern-2027`、`baidu-agent-algorithm-intern-j97505`、`alibaba-taotian-llm-intern-interview`、`xiaohongshu-llm-post-training-intern-2026`。

## 真实面经反映的追问习惯

1. **先让候选人讲项目，再把一个名词追成完整链路。** 例如从 RAG 继续问清洗、chunk、召回与上线，而不是在多个名词间横跳。（`bytedance-llm-algorithm-intern-interview`、`alibaba-taotian-llm-intern-interview`）
2. **不断追问“为什么选它”。** 从 GRPO/PPO、LoRA rank、NF4 到量化和动态批处理，选型理由与约束比术语定义更重要。（`bytedance-llm-algorithm-intern-interview`、`bytedance-llm-daily-intern-interview`、`meituan-llm-intern-interview`、`tencent-llm-algorithm-second-interview`）
3. **要求量化项目事实。** 数据多少、结构如何、硬件与显存怎样、效果如何验证，都是核对真实参与度的抓手。（`tencent-llm-algorithm-second-interview`）
4. **把算法与故障现象连接。** 会从延迟仍高、注意力偏移、梯度爆炸、KV Cache 污染等现象追问定位过程和解决依据。（`bytedance-llm-algorithm-intern-interview`、`tencent-llm-algorithm-second-interview`）
5. **Agent 场景追调度与评估，不只问“会不会调用工具”。** 会问 fallback、planning 与 hallucination 怎么测。（`alibaba-taotian-llm-intern-interview`、`baidu-agent-algorithm-intern-j97505`）

## 面试官使用边界

- 这些材料只决定岗位权重、专业判断与真实问法习惯，不替代本场项目陈述。
- 开场方向只能由“本场项目陈述 + 对应岗位方向”产生，禁止根据仓库内容出题。
- 库中未出现的企业标准或面试习惯不得自行补写。
