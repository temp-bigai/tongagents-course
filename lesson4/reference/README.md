# reference/ — SDK 源码节选（只读，供阅读）

**为什么要复制出来**：课程环境里 `tongagents` 以 wheel 安装，模块是 Cython 编译后的
`.so` 二进制（可以在 `.venv/lib/python3.12/site-packages/tongagents/` 里看一眼，
全是 `*.so`）——直接翻 site-packages **读不到源码**，所以这里附上与本课相关的
SDK 源文件。以环境实际安装的版本为准，本目录只作阅读参考，**不要修改、
不要 import**。

## 阅读顺序与文件对照

| 顺序 | 本目录文件 | SDK 内原始路径 | 读什么 |
|---|---|---|---|
| 1 | `stateless_react_agent.py` | `tongagents/agents/llm_agent/stateless_react_agent.py` | **ReAct 循环本体**：`__init__`（`tool_identifier_list` 逐个去 ToolManager 取实例）、`plan` 节点（`self.llm.request(input, tools=...)` —— 模型调用）、`_process_blocking_model_message`（有 `tool_calls` → `ToolAction`；有文本 → `TextAction`）、`_tool_call`（工具分发）。你要在 `cli_file_sample.py` 里接的两根线都从这里来 |
| 2 | `tool_manager.py` | `tongagents/tools/tool_manager.py` | **工具注册**：`tool_classes` 全局注册表、`register_tool(name, cls)`、`get_tool_instance(name)`（TODO(6) 与 Agent 构造之间的桥） |
| 3 | `base.py` | `tongagents/tools/base.py` | **工具基类**：`Tool` 的 ClassVar 三件套（`name` / `description` / `parameters`）、`call()` 的校验/重试协议、`_do_call` 抽象方法（TODO(1)-(5) 实现的就是它） |

建议对照方式：左边开你自己的 `tools/write_file_tool.py`，右边开 `base.py`
看 `call()` 怎么调 `_do_call`；再开 `stateless_react_agent.py` 找 `plan` / `_tool_call`，
对着 `cli_file_sample.py` 的 TODO(7)(8) 看"模型调用 → 工具执行 → 结果回填 → 最终回答"
在哪几行发生。
