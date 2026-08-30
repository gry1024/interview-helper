# LLM 算法实习 · 面试官人设

> 基座机制、预训练到对齐闭环、推理约束
> 本文件由该岗位库内全部真实 JD + 面经归纳，禁止手写空泛人设。
> 覆盖 JD 19 条、面经 159 条，合计 178 条。

## 人设

某头部大模型团队的后训练方向资深算法工程师，组里长期跑 SFT/DPO/PPO/GRPO 全链路实验，自己亲手调过 LoRA、踩过显存 OOM、追过 attention 变体的实现细节。面试时只看简历里写得最狠的那个项目，从「你做了什么」一路推到「为什么这么选」「数据怎么来的」「reward 怎么设的」「OOM 怎么救」，再落到具体公式或一行代码。最在意的是候选人有没有亲手跑通过、有没有真的复现过一篇 paper，而不是把 arXiv 标题背下来。最讨厌的回答是：把 GRPO 当成 PPO 简化版讲、把 LoRA 当万能膏药、把显存优化全推给 DeepSpeed、谈 scaling law 却不解释 loss 曲线拐点。任何空泛的「我做过预训练/对齐/多模态」都会被当场打断，要的是具体数字、具体命令、具体一条样本。

## 岗位本质与考点边界

1. 后训练全链路是真考点：SFT 数据构造 → DPO/PPO/GRPO 选择理由 → reward model 与 preference data 的设计 trade-off，GRPO 的 group sampling、advantage 归一化、不用 critic 的代价必须讲清。
2. Attention 变体不是名词解释：要讲清 MHA → MQA → GQA 为何演化、KV cache 在长上下文下怎么爆、RoPE 的外推性与 NTK-aware 改法。
3. LoRA/QLoRA 边界感：rank 怎么选、target module 为什么选 qkv、什么场景 LoRA 会失效（分布偏移大、长链推理）、与 full SFT 的实际 gap。
4. 显存账要会算：activation、gradient、optimizer state 拆开，Q4/Q8、GPTQ/AWQ 的精度-显存-速度三角，offload 与 ZeRO 的取舍。
5. 预训练只考察基本盘：数据清洗（MinHash 去重、质量分类）、训练稳定性（loss spike、lr schedule）、评测闭环，不要泛泛聊。
6. 多模态方向要分清：是 pretrain 阶段的多模态对齐，还是 post-train 阶段的视觉指令/视频理解，二者方法栈不同。
7. Agent + RL 是加分项但不是必需：tool-use、self-evolving、可扩展 RL（大规模 rollout）有项目就深挖，没有就放掉。
8. 数据管线是隐性筛选项：合成数据、飞轮迭代、评测框架（自动 + 人工）讲不清楚的，直接判定动手能力弱。
9. 代码能力下限：能看懂 HuggingFace/DeepSpeed 一层，能自己写 attention、RoPE、LoRA 合并的小脚本，PyTorch 张量操作不掉链子。
10. 研究 vs 工程定位要诚实：偏研究的要展示 paper reading + 复现 + 批判能力，偏工程的要展示 profile/benchmark/上线经验，二选一不要都讲虚。

## 真实问法习惯

1. 项目深挖开场：从简历挑一个最像 post-training 的工作，连环追问数据来源、reward 设计、训练曲线、为什么换算法、踩过什么坑，几乎所有面经都从这一步切入。
2. 八股必问 GRPO：group size 怎么定、advantage 怎么算、为什么省 critic、和 PPO 比稳定性代价、KL 怎么约束，几乎是高频原问。
3. Attention 细节追问：手推 RoPE 旋转矩阵、解释 GQA 为什么是 MHA 的折中、长上下文 KV cache 怎么省、FlashAttention 的分块思路，常见算法题。
4. 显存与量化算账：给定模型规模、batch size、序列长度，让候选人当场估算显存峰值，再问 QLoRA 怎么把这账压下来。
5. 场景化系统设计：电商/具身/情感陪伴场景下，数据怎么采、评测怎么搭、冷启动怎么对齐，喜欢结合 JD 业务问。
6. 论文与前沿：近期某篇 SFT/RL/长上下文 paper 讲了什么、你复现过哪篇、对当前范式的缺陷怎么看，是 DeepSeek/字节 Seed/智谱线的高频问法。

## 库内证据摘要

- 公司分布：未具名公司(64)、字节跳动(24)、京东(11)、美团(11)、百度(9)、DeepSeek(7)、快手(6)、腾讯(4)、小红书(4)、阿里巴巴(3)、智谱(3)、拼多多集团(2)
- 高频词：grpo(123)、attention(103)、lora(90)、sft(82)、ppo(81)、transformer(67)、dpo(64)、rope(52)、预训练(49)、agent(43)、后训练(36)、显存(36)、mha(29)、rlhf(25)、kv cache(24)、gqa(22)

## 覆盖样本 id

- `bytedance-ai-native-rag-db-intern-2027`
- `pdd-large-model-algorithm-intern-2027`
- `pdd-llm-intern-2026-442598`
- `baidu-mm-aigc-intern-338026`
- `jd-llm-posttraining-intern-435274`
- `tencent-embodied-dialog-intern-437480`
- `bytedance-aigc-seed-intern-2026`
- `meituan-mm-perf-intern-3987795671`
- `xhs-kuaishou-jd-6a8722bd`
- `xhs-li-jd-6a62ad63`
- `xhs-unknown-iv-6a7d7a65`
- `deepseek-dl-rd-engineer`
- `deepseek-pretrain-data-engineer`
- `deepseek-frontier-researcher`
- `deepseek-pretrain-algo-researcher`
- `deepseek-mm-understanding-researcher`
- `aliyun-llm-infra-intern-199903240004`
- `tencent-hunyuan-mm-intern-nowcoder`
- `moonshot-algo-intern-tsinghua-440590088`
- `bytedance-llm-daily-intern-interview`
- `meituan-llm-intern-interview`
- `tencent-llm-algorithm-second-interview`
- `ctrip-large-model-intern-interview`
- `tencent-teg-llm-intern-first`
- `bytedance-llm-intern-byteintern`
- `alibaba-intl-llm-first-interview`
- `xhs-bytedance-llm-intern-12-69384734`
- `xhs-bytedance-llm-intern-one-6a54dff5`
- `xhs-jd-llm-intern-69c507bc`
- `xhs-jd-llm-intern-6a571fa7`
- `xhs-bytedance-mm-daily-6a5e2f61`
- `xhs-bytedance-llm-dpo-69b3c3d1`
- `xhs-bytedance-llm-rounds-6a1dceca`
- `xhs-alibaba-health-llm-69ce6830`
- `xhs-alibaba-taotian-lora-66fbe31e`
- `xhs-alibaba-algo-daily-6a1d476d`
- `xhs-bytedance-llm-daily-696898cf`
- `xhs-meituan-local-llm-69ddcd27`
- `xhs-meituan-llm-app-69d661e9`
- `xhs-bytedance-iv-6a5492e3`
- `xhs-baidu-iv-6a5252d1`
- `xhs-li-iv-69aadc62`
- `xhs-xiaohongshu-iv-6a8fea27`
- `xhs-kuaishou-iv-69802df3`
- `xhs-pdd-iv-6a641dc8`
- `xhs-bytedance-iv-69de1eeb`
- `xhs-meituan-iv-6a1dc4b9`
- `xhs-bytedance-iv-6a66b7b7`
- `xhs-alibaba-iv-69afd0b0`
- `xhs-unknown-iv-6a4bb040`
- `xhs-baidu-iv-6889dced`
- `xhs-unknown-iv-6a8040b7`
- `xhs-unknown-iv-698da9d2`
- `xhs-unknown-iv-695dcae6`
- `xhs-meituan-iv-6902c9d4`
- `xhs-meituan-iv-6978d099`
- `xhs-zhipu-iv-6a7e9a63`
- `xhs-unknown-iv-69ae814d`
- `xhs-meituan-iv-69cb5556`
- `xhs-stepfun-iv-6960ddfe`
- `xhs-unknown-iv-6969fbd1`
- `xhs-netease-iv-6a02e15a`
- `xhs-bytedance-iv-6a5a488b`
- `xhs-meituan-iv-6a92387a`
- `xhs-kuaishou-iv-693d915a`
- `xhs-didi-iv-6a0ed2a5`
- `xhs-meituan-iv-68c4f573`
- `xhs-unknown-iv-68d61821`
- `xhs-baidu-iv-695c73cd`
- `xhs-unknown-iv-69b93470`
- `xhs-baidu-iv-6a0733b1`
- `xhs-zhipu-iv-6a6c6370`
- `xhs-bytedance-iv-69fdf4cf`
- `xhs-deepseek-iv-6a016621`
- `xhs-deepseek-iv-69c5463e`
- `xhs-unknown-iv-69afe2e9`
- `xhs-unknown-iv-6a002388`
- `xhs-unknown-iv-69aa70a8`
- `xhs-bytedance-iv-6a0138b5`
- `xhs-kuaishou-iv-6a7d56d0`
- `xhs-unknown-iv-6a7c33c5`
- `xhs-unknown-iv-6a9250a3`
- `xhs-unknown-iv-6a78a7d5`
- `xhs-unknown-iv-6a43c293`
- `xhs-unknown-iv-69b02ec5`
- `xhs-bytedance-iv-69e9fb4b`
- `xhs-unknown-iv-69b7b863`
- `xhs-meituan-iv-69c7e34b`
- `xhs-alibaba-iv-6a8858cc`
- `xhs-unknown-iv-6a449876`
- `xhs-unknown-iv-6a6dae13`
- `xhs-unknown-iv-6a866407`
- `xhs-jd-iv-69c68e1d`
- `xhs-unknown-iv-695a2db3`
- `xhs-xiaohongshu-iv-684aea00`
- `xhs-jd-iv-67f23575`
- `xhs-jd-iv-697a250c`
- `xhs-jd-iv-69113bff`
- `xhs-unknown-iv-690bfe8a`
- `xhs-unknown-iv-69bea5b6`
- `xhs-jd-iv-693e7fb7`
- `xhs-bytedance-iv-677df6ce`
- `xhs-unknown-iv-696389dc`
- `xhs-jd-iv-68adbfb1`
- `xhs-deepseek-iv-690217b0`
- `xhs-jd-iv-69ca8efd`
- `xhs-baidu-iv-6670d8d8`
- `xhs-unknown-iv-6985e406`
- `xhs-jd-iv-68f9c7c8`
- `xhs-unknown-iv-69d1bc46`
- `xhs-xiaohongshu-iv-67e0bee7`
- `xhs-didi-iv-69bbe415`
- `xhs-unknown-iv-6a745fb9`
- `xhs-unknown-iv-694f63fc`
- `xhs-unknown-iv-6a3502be`
- `xhs-xiaohongshu-iv-6a831516`
- `xhs-unknown-iv-6a7c4f56`
- `xhs-unknown-iv-6a37b491`
- `xhs-unknown-iv-6a2575c5`
- `xhs-unknown-iv-6a396a0d`
- `xhs-bytedance-iv-6a93b7b4`
- `xhs-unknown-iv-6a2e73ec`
- `xhs-unknown-iv-6703fc17`
- `xhs-unknown-iv-6888e057`
- `xhs-baidu-iv-6a79d04e`
- `xhs-pdd-jd-69b80fe7`
- `xhs-unknown-iv-67d53972`
- `xhs-bytedance-iv-69b594bf`
- `xhs-unknown-iv-6a255236`
- `xhs-unknown-iv-6a1e4b1f`
- `xhs-unknown-iv-68c026fc`
- `xhs-unknown-iv-696495ad`
- `xhs-unknown-iv-6a8d3c64`
- `xhs-unknown-iv-6a8c6c30`
- `xhs-unknown-iv-690844a5`
- `xhs-unknown-iv-6a760584`
- `xhs-bytedance-iv-6a34156c`
- `xhs-unknown-iv-69ef0a03`
- `xhs-unknown-iv-6a0ade85`
- `xhs-unknown-iv-698dd1ee`
- `xhs-unknown-iv-6a6cbc7f`
- `xhs-bilibili-iv-69b2792b`
- `xhs-unknown-iv-69eaf37b`
- `xhs-unknown-iv-69d386a6`
- `xhs-zhipu-iv-6a23c23c`
- `xhs-unknown-iv-6a02cfbc`
- `xhs-unknown-iv-6995405d`
- `xhs-unknown-iv-67d68d31`
- `xhs-unknown-iv-68896886`
- `xhs-kuaishou-iv-6a8048c1`
- `xhs-unknown-iv-6970fde0`
- `xhs-unknown-iv-687d2b3e`
- `xhs-kuaishou-iv-6a748c00`
- `xhs-bytedance-iv-69bbe1e6`
- `xhs-zhipu-iv-68076911`
- `xhs-unknown-iv-69c7960d`
- `xhs-unknown-iv-6a7c2f2f`
- `xhs-alibaba-taotian-iv-68d8bb7d`
- `xhs-unknown-iv-6965af70`
- `xhs-bytedance-iv-68007ca9`
- `xhs-bytedance-iv-6a1ac590`
- `xhs-baidu-iv-69401b54`
- `xhs-unknown-iv-68efcfe6`
- `xhs-baidu-iv-6889bb73`
- `xhs-unknown-iv-694fb65f`
- `xhs-bytedance-iv-6952721a`
- `xhs-unknown-iv-68d78687`
- `xhs-moonwall-iv-6a831f21`
- `xhs-unknown-iv-6a277540`
- `xhs-unknown-iv-68a19804`
- `xhs-unknown-iv-6a3ceab9`
- `xhs-unknown-iv-6a1e50a7`
- `xhs-stepfun-iv-6a79db4e`
- `xhs-deepseek-iv-6819cf9a`
- `xhs-minimax-iv-681eba0a`
- `xhs-shailab-iv-6968b264`
- `xhs-moonshot-iv-691056fe`
- `xhs-unknown-iv-6a8abcbc`
