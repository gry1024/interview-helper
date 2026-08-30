# 手撕题 tool（code_exercise）

需要核实「会不会写」，且该实现属于已搜集面经常考手撕时，才调用 `code_exercise`。
题只能从服务端题库取，禁止现场编题面、starter 或无关算法题。

## 何时调用

- 当前方向已经问到机制，需要看学生能否写出对应前向（如 Attention → Multi-Head / scaled；LLaMA 组件 → RoPE / RMSNorm / SwiGLU；推理 → KV Cache / PagedAttention；微调 → LoRA）。
- 面经常考、且贴着本场方向与项目。禁止链表、排序、背包、二叉树等无关题。
- 同一场同一 `exercise_id` 不重复。一轮最多打开一题。
- 学生刚提交代码的这一轮只评价文本，不要再打开新题。
- 学生说「手撕 / 请打开题 / 我想写」或在对话框贴了代码时，必须打开编辑器；普通问答禁止把代码当口答。
- 与 `code_inspect` 并列：查仓库真伪用 inspect，核实会不会写用 exercise。

## 参数

- 优先 `exercise_id`（必须是题库 id）。
- 否则给 `topic`（如 `RoPE`、`KV cache`、`LoRA`），由服务端匹配。
- 不要自拟 prompt / starter；匹配失败时继续口头追问。
