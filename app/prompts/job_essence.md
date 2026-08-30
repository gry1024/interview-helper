# LLM 算法实习岗位本质与面试官前置知识

> 本文件仅由 `app/jd/jds.json` 与 `app/jd/interviews.json` 的真实来源归纳。
> 括号内 id 是每条主张的证据索引；样本扩充后必须同步复核本文件。
> 主库已剔除官网/职位页写明仅硕博或 PhD 的条目；那些样本只在 `app/jd/_filtered_out.json`。

## 通用筛人标准

1. **不只会复述架构，还能沿数据流解释机制与取舍。** 候选人应能从输入、表示、注意力到输出解释 Transformer，并说明具体优化解决了什么瓶颈，而不是只背定义。（`pdd-large-model-algorithm-intern-2027`、`pdd-llm-intern-2026-442598`、`bytedance-llm-daily-intern-interview`、`ctrip-large-model-intern-interview`、`baidu-wence-llm-second-interview`、`xhs-bytedance-llm-intern-12-69384734`、`xhs-bytedance-llm-rounds-6a1dceca`）
2. **真正跑过训练或后训练闭环。** 重点核对数据处理、Pre-training、SFT、Post-training/RL、评估与迭代是否形成闭环，以及每一步如何证明有效。（`pdd-large-model-algorithm-intern-2027`、`jd-llm-posttraining-intern-435274`、`aliyun-agent-algo-intern-440646`、`alibaba-tstar-agent-intern-439692`、`tencent-teg-llm-intern-first`、`xhs-bytedance-mm-daily-6a5e2f61`、`xhs-jd-llm-intern-6a571fa7`、`xhs-bytedance-llm-daily-696898cf`）
3. **数据不是背景材料，而是算法结果的一部分。** 要能说清数据来源、清洗、结构、合成、过滤、有效性验证与多样性控制，并解释数据决策如何影响模型行为。（`tencent-embodied-dialog-intern-437480`、`tencent-llm-algorithm-second-interview`、`shunfeng-llm-intern-interview`、`baidu-wence-llm-second-interview`、`xhs-alibaba-health-llm-69ce6830`、`xhs-alibaba-taotian-agent-69dbbf4b`、`xhs-bytedance-llm-dpo-69b3c3d1`）
4. **方法选择必须有可验证理由。** 对 LoRA、PPO/GRPO/DPO、量化、推理框架等选择，要能交代约束、替代方案、稳定性或资源代价和评估证据。（`jd-llm-posttraining-intern-435274`、`bytedance-llm-algorithm-intern-interview`、`tencent-teg-llm-intern-first`、`alibaba-intl-llm-first-interview`、`bytedance-llm-intern-byteintern`、`xhs-bytedance-llm-intern-one-6a54dff5`、`xhs-alibaba-taotian-lora-66fbe31e`、`xhs-meituan-llm-app-69d661e9`）
5. **工程能力要落到资源与上线约束。** 除算法效果外，还要理解显存、延迟、吞吐、上下文长度、分布式训练和推理服务之间的权衡。（`meituan-mm-perf-intern-3987795671`、`bytedance-llm-daily-intern-interview`、`tencent-llm-algorithm-second-interview`、`bytedance-llm-intern-byteintern`、`xhs-bytedance-llm-dpo-69b3c3d1`、`xhs-meituan-local-llm-69ddcd27`、`xhs-jd-llm-intern-69c507bc`）
6. **Agent / RAG 项目要能说清闭环与失败处理。** 包括检索链路、工具调用调度、评估维度、异常 fallback 与 memory 设计。（`bytedance-ai-native-rag-db-intern-2027`、`baidu-agent-algorithm-intern-j97505`、`aliyun-llm-app-dev-intern-2027`、`alibaba-agent-dev-intern-2027`、`kuaishou-llm-daily-intern-second`、`alibaba-taotian-llm-intern-interview`、`xhs-tencent-agent-69cbee68`、`xhs-startup-agent-69ca958d`、`xhs-ant-llm-intern-6a86fbea`）

## 按岗位方向加载

### `llm-algo`：基座与通用大模型算法

- 核心链路：Transformer 组件与数据流 → 预训练/微调/对齐 → 评估可信度 → 推理或业务落地。
- 深挖重点：组件为什么这样设计、训练阶段如何衔接、失败现象如何定位、改动是否有对照实验。
- 证据：`pdd-large-model-algorithm-intern-2027`、`pdd-llm-intern-2026-442598`、`baidu-mm-aigc-intern-338026`、`bytedance-aigc-seed-intern-2026`、`ctrip-large-model-intern-interview`、`meituan-llm-intern-interview`、`baidu-wence-llm-second-interview`、`xhs-bytedance-llm-intern-12-69384734`、`xhs-bytedance-llm-rounds-6a1dceca`。

### `training`：训练、后训练与对齐

- 核心链路：数据构造与过滤 → SFT → Reward/偏好信号 → PPO/GRPO/DPO 等 RL → 稳定性与效果评估。
- 深挖重点：奖励是否真的衡量正确性、如何防止 reward hacking、算法选择依据、分布式资源约束。
- 证据：`jd-llm-posttraining-intern-435274`、`aliyun-agent-algo-intern-440646`、`alibaba-tstar-agent-intern-439692`、`tencent-llm-algorithm-second-interview`、`tencent-teg-llm-intern-first`、`alibaba-intl-llm-first-interview`、`bytedance-llm-intern-byteintern`、`xhs-bytedance-llm-intern-one-6a54dff5`、`xhs-bytedance-llm-dpo-69b3c3d1`、`xhs-ant-llm-intern-6a86fbea`、`xhs-meituan-llm-summer-69fc448f`。

### `rag`：检索增强与 Agent 应用

- 核心链路：语料清洗 → chunk → embedding/召回 → rerank → 生成 → 线上评估。
- 深挖重点：切分策略为什么适合数据、召回率如何测、Embedding 与 Rerank 各自承担什么、上线后瓶颈在哪里。
- Agent 项目还应核对任务拆解、工具调用、闭环执行、fallback 和长链路失败处理。
- 证据：`bytedance-llm-algorithm-intern-interview`、`bytedance-ai-native-rag-db-intern-2027`、`baidu-agent-algorithm-intern-j97505`、`aliyun-llm-app-dev-intern-2027`、`alibaba-agent-dev-intern-2027`、`alibaba-agent-app-intern-439376`、`kuaishou-llm-agent-intern-441964`、`bytedance-ai-search-agent-intern-386087`、`bytedance-agent-dev-intern-435369`、`transsion-agent-intern-444729`、`kuaishou-llm-daily-intern-second`、`tme-nlp-intern-interview`、`shunfeng-llm-intern-interview`、`sensetime-llm-app-intern-interview`、`baidu-wence-llm-second-interview`、`xhs-tencent-agent-69cbee68`、`xhs-alibaba-taotian-agent-69dbbf4b`、`xhs-startup-agent-69ca958d`、`xhs-alibaba-algo-daily-6a1d476d`。

## 真实面经反映的追问习惯

1. **先让候选人讲项目，再把一个名词追成完整链路。** 例如从 RAG 继续问清洗、chunk、召回与上线，而不是在多个名词间横跳。（`bytedance-llm-algorithm-intern-interview`、`tme-nlp-intern-interview`、`baidu-wence-llm-second-interview`、`xhs-tencent-agent-69cbee68`、`xhs-jd-llm-intern-6a571fa7`）
2. **不断追问“为什么选它”。** 从 GRPO/PPO、LoRA rank、DPO 到量化和动态批处理，选型理由与约束比术语定义更重要。（`bytedance-llm-intern-byteintern`、`bytedance-llm-daily-intern-interview`、`meituan-llm-intern-interview`、`tencent-llm-algorithm-second-interview`、`alibaba-intl-llm-first-interview`、`tencent-teg-llm-intern-first`、`xhs-bytedance-llm-intern-one-6a54dff5`、`xhs-alibaba-algo-daily-6a1d476d`）
3. **要求量化项目事实。** 数据多少、结构如何、硬件与显存怎样、效果如何验证，都是核对真实参与度的抓手。（`tencent-llm-algorithm-second-interview`、`tme-nlp-intern-interview`、`huolala-llm-first-interview`、`xhs-bytedance-llm-dpo-69b3c3d1`、`xhs-jd-llm-intern-69c507bc`、`xhs-meituan-local-llm-69ddcd27`）
4. **把算法与故障现象连接。** 会从延迟仍高、召回错、生成错、KV Cache 污染、输出变长或拒答等现象追问定位过程和解决依据。（`bytedance-llm-algorithm-intern-interview`、`tencent-llm-algorithm-second-interview`、`baidu-wence-llm-second-interview`、`kuaishou-llm-daily-intern-second`、`xhs-bytedance-llm-intern-one-6a54dff5`、`xhs-meituan-llm-summer-69fc448f`、`xhs-ant-llm-intern-6a86fbea`）
5. **Agent 场景追调度与评估，不只问“会不会调用工具”。** 会问 fallback、planning 与 hallucination 怎么测，以及多 Agent 冲突和超时兜底。（`alibaba-taotian-llm-intern-interview`、`baidu-agent-algorithm-intern-j97505`、`kuaishou-llm-daily-intern-second`、`sensetime-llm-app-intern-interview`、`huolala-llm-first-interview`、`xhs-startup-agent-69ca958d`、`xhs-alibaba-algo-daily-6a1d476d`、`xhs-meituan-llm-app-69d661e9`）

## 面试官使用边界

- 这些材料只决定岗位权重、专业判断与真实问法习惯，不替代本场项目陈述。
- 开场方向只能由“本场项目陈述 + 对应岗位方向”产生，禁止根据仓库内容出题。
- 库中未出现的企业标准或面试习惯不得自行补写。
