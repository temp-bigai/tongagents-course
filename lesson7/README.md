# 实战任务：将搜索工具升级为“子智能体”

## 1. 背景与目标
如课程 PPT 中所述，当主 Agent 直接调用“网络搜索”等会返回巨量原始文本的工具时，会面临上下文爆炸、核心推理能力被稀释、以及推理成本极高的问题。

本练习要求你为你现有的单 Agent 系统添加**子智能体机制（SubAgent）**：
- 将直接暴露给主 Agent 的网络搜索 Tool，**替换**成一个专注于搜索和提炼的 `Search SubAgent`。
- 主 Agent 遇到需要检索的问题时，调用 SubAgent，只获取提炼后的高价值精简总结，从而避免直接消化海量原始网页文本。

> **注意**：动手编码的代码**不需要**存放在本仓库的 `lesson7` 目录下。请直接在你基于之前课程和练习所创建的自有 Agent 仓库中进行演进。

## 2. 架构设计：动手前的开放性工程思考题

在真正开始动手写代码前，请结合课程 PPT，思考引入子智能体在框架设计上面临的诸多取舍：

1. **服务发现与触发机制**：主 Agent 怎么发现子 Agent 的存在，并知道何时调用它？是将它注入到系统指令中，还是通过 skill 披露？
2. **调用协议与 Schema 设计**：接口应该是什么样？模型 ID、System Prompt、Tools 等，哪些允许动态指定？哪些必须被框架写死？
3. **生命周期与交互模式**：子 Agent 是任务完成后立即销毁（Stateless），还是保持会话状态，允许主 Agent 进行多轮追问？
4. **并发与阻塞调度**：派发任务后，是否应该阻塞（Block）主 Agent？如果非阻塞，主 Agent 在等待期间如何挂起或处理其他逻辑？
5. **资源管控与成本熔断**：怎么避免主 Agent 陷入逻辑死循环，疯狂创建子 Agent 导致并发崩溃和成本爆炸？
6. **信息隔离 (Context Isolation)**：子 Agent 被唤起时，是否需要继承主 Agent 庞大的记忆？如何平衡信息充分与上下文冗余污染？

### 📝 要求一：你的设计选择
在动手编码前，请针对以上 6 个问题，给出你在设计自己的多智能体机制时的**选择及理由**。


## 3. 参考实现：Codex 的多智能体设计与源码分析

在设计和实现子智能体机制时，你可以参考业界真实落地的方案。以下是 Codex 多智能体相关的 Tool Schema 设计及代码实现路径，供阅读分析：

- **Tool Schema 设计**: [multi_agents_spec.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_spec.rs)
- **V1 机制实现**: [multi_agents 源码目录](https://github.com/openai/codex/tree/main/codex-rs/core/src/tools/handlers/multi_agents)
- **V2 机制实现**: [multi_agents_v2 源码目录](https://github.com/openai/codex/tree/main/codex-rs/core/src/tools/handlers/multi_agents_v2)

### Codex V1 与 V2 对比
Codex 多智能体工具在上层架构和接口上在 V1 和 V2 版本间发生了明显的变动。以下为两版的多智能体相关tool对比：

#### V1 版本核心工具
- **`spawn_agent`**: 创建子智能体。参数：`model`, `reasoning_effort`, `agent_type`（均非必填）。
- **`send_input`**: 向已创建的子智能体下发指令或消息。参数：`target`（必填）, `message`, `items`, `interrupt`。
- **`wait_agent`**: 等待子智能体完成任务。参数：`target`（必填）, `timeout_ms` 等。
- **`resume_agent`**: 唤醒或恢复处于挂起等状态的子智能体。参数：`id`（必填）。
- **`close_agent`**: 关闭子智能体。参数：`target`（必填）。

#### V2 版本核心工具
- **`spawn_agent`**: 创建并立即派发任务给子智能体。参数：**`task_name`**（必填）、**`message`**（必填）、`model`, `reasoning_effort`, `agent_type`。
- **`send_message`**: 向存活的子智能体发送消息。参数：`target`（必填）, `message`。
- **`followup_task`**: 向子智能体下发后续任务。参数：`target`（必填）, `message`。
- **`wait_agent`**: 等待来自活跃智能体的消息或更新。参数：`timeout_ms` 等。
- **`interrupt_agent`**: 打断子智能体当前的执行。参数：`target`（必填）。
- **`list_agents`**: 列出当前存活的智能体。参数：`path_prefix`。

### 📝 要求二：源码阅读与对比思考
结合上面的对比，深入阅读 Codex 的实现源码，并回答以下问题：

1. **工业界怎么做**：请分析 Codex 的代码，Codex 团队是如何处理上一节提到的“开放性工程思考题”中的各项挑战的？
2. **变动原因与目的**：思考并分析，Codex 为什么要将机制从 V1 演进为 V2？这种架构级别的变动（例如 `spawn_agent` 新增必填任务参数、工具拆分重组等）背后的原因和目的是什么？
3. **优缺点对比**：对比 Codex 的 V1 和 V2 机制，你认为这两种模式分别有什么优缺点？
