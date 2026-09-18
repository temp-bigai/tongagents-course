# 实战任务：智能体自进化

本节课程实战旨在为我们的 Agent 赋予持续学习与自适应的能力。我们将通过两个主要任务来实现这一目标：一是构建 Agent 的“持续学习”机制，让其具备跨会话的长效记忆与反思能力；二是通过 Hooks 机制实现 Agent 的“带内自进化”，允许 Agent 在运行时感知、扩展并修改自身的执行框架（Harness）。

## 实战任务 1：实现“持续学习”机制

**目标**：解决 Agent “屡教不改”的问题，让其在遇到连续的相同错误或用户的连续不满时，能够自动触发学习机制，总结教训，以防未来再犯。

### 要求
当发生以下情况时，触发 Agent 的自动学习与反思机制：
- 连续 2 次遇到并解决相同类型的问题。
- 用户对同一件事连续 2 次表示不满或失望。

### 思考与设计
在动手编码之前，请先思考以下架构设计层面的问题，并给出你的技术选型与理由：

1. **学习模式的选择**：
   - 是让主 Agent 在执行任务过程中进行**同步学习**（可能会增加当前任务的延迟并消耗上下文），还是启动 Subagent 进行**异步学习**（不阻塞当前任务的执行）？
2. **经验持久化的位置**：
   - 学习到的“经验教训”应该存储在哪里？(例如：`skill` 文件、专用的 `memory` 数据库、`AGENTS.md`、或者项目相关文档？)
   - 系统该如何自动为不同类型的经验选择最合适的存储位置？
3. **经验的加载与召回**：
   - Agent 该如何加载学习到的经验？是选择在启动时**被动全量加载**（可能导致上下文臃肿），还是在执行时根据当前任务**主动检索**？
4. **机制的稳定性与防遗忘**：
   - 在长对话（长上下文）中，如何确保 Agent 不会遗忘“学习指令”和“学习机制”本身？
5. **(其他问题)** 你还能想到哪些潜在的问题？例如：如何避免错误经验的污染？经验冲突时如何解决？

如果你计划采用 Subagent 进行异步学习，可以参考并复用在 `lesson7` 实践中实现的 Subagent 机制。

---

## 实战任务 2（进阶）：实现基于 Hooks 的自进化

**目标**：允许 Agent 在运行时借助于hooks感知、扩展并修改自身的执行框架（Harness），进而实现真正意义上的“自进化”。

### 要求

#### 阶段 A：给执行框架 (Harness) 添加 Hooks 机制
修改现有的 Harness 框架，引入生命周期钩子 (Lifecycle Hooks)。要求支持在以下关键节点注册并执行特定的外部脚本/函数：
- `before_llm_call` / `after_llm_call`
- `before_tool_execution` / `after_tool_execution`
- `before_stop`

#### 阶段 B：通过 Hooks 让 Agent 自进化 Harness
给 Agent 下达类似这样的任务：**“每次修改代码后，必须确保没有任何语法警告（如通过 Ruff 或 ESLint 检查）”**。

Agent 不应仅仅将此要求记录在上下文中，而是应该：
1. 编写一个执行代码检查（如 `ruff check`）的 Hook 脚本。当检查失败时，该脚本返回拦截 Agent 退出的信号及详细报错信息。
2. 将此 Hook 脚本动态注册到当前项目的 Harness 中（例如绑定至 `after_tool_execution` 或 `before_stop`）。
3. 验证功能：当用户下达下一个任务后，Harness 会在退出前自动运行该 Hook。如果检查未通过，Harness 会拒绝 Agent 的退出请求，并强制要求其修复报错。

### 架构设计
在引入 Hooks 机制前，同样需要先思考架构与安全设计的问题，并给出你的技术选型和理由。

1. **Agent 对框架的感知**：
   - 如何让 Agent 感知到自己拥有的 Hooks 机制及其输入输出协议 (Schema)？是通过 System Instruction、Skill、提供专用的 Tool，还是指派一个专门负责维护框架的 Subagent？
2. **防“卡死”机制**：
   - Agent 作为代码编写者，有可能会写出导致无限循环、语法错误或直接 Crash 的 Hook 代码。如何从机制上避免 Agent 修改 Hooks 后把自己卡死无法恢复？
3. **利用 Hooks 解决“遗忘”问题**：
   - 是否可以通过引入 Hooks 机制，来解决上一个任务中“Agent 遗忘自己的学习机制”的问题？
4. **(其他问题)** 还有哪些问题需要考虑？例如：多个 Hook 之间的执行顺序如何管理？Hook 的执行权限如何控制？


> **参考资料**：
> - Codex Hooks 文档：[https://learn.chatgpt.com/docs/hooks](https://learn.chatgpt.com/docs/hooks)
> - Codex Hooks Schema：[https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated](https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated)
> - *Codex 支持的 Hooks 包括：`PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `UserPromptSubmit`, `SubagentStop`, `Stop`, `Interrupt`, `SessionStart`, `SubagentStart`, `SessionEnd`。*
