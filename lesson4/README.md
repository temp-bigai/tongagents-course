# Lesson 4 作业：仿照 cli-sample 重写一个本地文件 CLI Agent

`../cli-sample/` 是参照物：单文件 REPL + Agent 薄壳 + `StatelessReactAgent` + 6 个本地工具。本作业把它的结构**自己重写一遍**：`tools/` 下的 6 个工具全部自己实现，Agent 的构造与返回值提取自己接线；SDK 内部的 ReAct 循环（模型调用 → 工具分发 → 结果回填）保持黑盒使用，但通过 `reference/` 源码读懂它替你做了什么。

## 作业概览

- **作业目标**：仿照 cli-sample 自己重写一个 CLI 客户端，掌握 CLI 应用的基本组成——REPL 交互、ReAct 循环、模型调用、工具注册与工具结果回填，最终得到一个本地可运行、能真正完成文件操作的 CLI Agent。
- **核心任务**：参考 cli-sample 的结构，完成 react loop 接线、工具注册、6 个本地工具（read/write/edit/bash/glob/grep）。
- **关键要求**：参考 cli-sample 的组织方式，但**自行完成代码重写**；不得用硬编码答案或伪造工具调用代替真实流程（自测用 FakeLLM 顶替模型驱动**真实的** SDK 循环，工具必须真实执行，伪造不了）。
- **最终效果**：运行客户端后，用户在终端自然语言交互，Agent 按需选择并执行工具，完成任务后给出最终回答：

```text
>>> 在 /tmp/lesson4-demo 下创建 notes.md，写入"今天学了 ReAct 循环"
  已创建 /tmp/lesson4-demo/notes.md，内容为"今天学了 ReAct 循环"。
>>> 把 notes.md 里的"循环"改成"loop"
  已修改, 文件现在的内容是: 今天学了 ReAct loop
>>> demo 目录里哪些文件提到 loop？
  只有 1 个文件提到 "loop"：notes.md（第 1 行）
```

## ReAct 循环在 SDK 里是怎么转的

你写的每一部分都在这条链上（对照 `reference/stateless_react_agent.py`）：

```text
REPL (cli_file_sample.py, 已给)
  └─ CliFileAgent.step(query)              TODO(8): 从 actions 里取最终文本
      └─ StatelessReactAgent.step(input)   ← SDK 黑盒, 构造接线是 TODO(7)
           ├─ plan 节点:    llm.request(messages, tools=注册表全部工具)   ← 模型调用
           │     └─ 无 tool_calls → TextAction(is_final_response=True)   ← 最终回答
           └─ execute 节点: _tool_call → ToolManager 实例.call(params)   ← 工具分发
                 └─ ToolResultMessage 回填进下一轮 messages              ← 结果回填
```

两条契约红线（`check_homework.py` 用于校验）：

1. **工具失败不抛异常**：`_do_call` 失败时返回 `"error: ..."` 字符串——错误要能回传给模型让它自己纠正；抛异常会打断整轮对话；
2. **先注册才能被选用**：工具必须经 `register_tool` 进入 `ToolManager`（TODO(6)），Agent 构造时按 `tool_identifier_list` 逐个取实例，没注册的名字直接报错。

## 脚手架

lesson4/ 已提供（环境方式与 lesson1 / cli-sample 相同：本地 wheel，不走 nexus）：

```text
lesson4/
├── README.md               # 本文件
├── pyproject.toml          # 自身依赖 (python-dotenv); tongagents 从 ../wheels/ 安装
├── reference/              # SDK 源码节选 (只读) — 为什么: 见 reference/README.md
├── tools/
│   ├── __init__.py         # TODO(6): register_default_tools 注册 6 工具
│   ├── read_file_tool.py   # 已给完整样例 (函数 + schema + 注册三件套)
│   ├── write_file_tool.py  # TODO(1)
│   ├── edit_file_tool.py   # TODO(2)
│   ├── bash_tool.py        # TODO(3)
│   ├── glob_tool.py        # TODO(4)
│   └── grep_tool.py        # TODO(5)
├── check_homework.py       # 8 项自测, 不需要 LLM Key 和网络
└── cli_file_sample.py      # TODO(7)(8): Agent 构造 / 返回值提取; REPL 已给
```

每个 TODO 的注释里都有分步提示；工具行为对照 `../cli-sample/tools/` 同名工具（可读，但要自己写）。

## 第 0 步：确认起点

- 仓库根目录 `wheels/` 已放入维护者提供的 tongagents wheel（流程见 `lesson1/INSTALL.md`，本课不需要 tongagents_cli）；
- 初始化本课环境（首次使用执行一次，与 lesson1 同一套流程）：

```bash
cd lesson4
python3 -m venv .venv && source .venv/bin/activate
pip install ../wheels/tongagents-*.whl   # 先装 wheel (SDK)
pip install -e .                         # 再装本课自身依赖 (python-dotenv)
```

> 装了 uv 的同学可以等价使用：`uv venv && source .venv/bin/activate`，
> `uv pip install ../wheels/tongagents-*.whl && uv pip install -e .`，
> 运行时用 `python ...`（已激活）或 `uv run --no-sync python ...`（未激活）。
> 顺序很重要：先 wheel 再 `-e .`，否则 pip 会去公网找 tongagents 而失败。

- `.env` 沿用 cli-sample 的那份（`cli_file_sample.py` 会自动加载 `../cli-sample/.env`）。

## 第 1 步：读参照物

1. `reference/` 三个 SDK 源文件（顺序与对照表见 `reference/README.md`）——ReAct 循环本体 / 工具注册 / 工具基类；
2. `../cli-sample/cli_sample.py`——你要重写的目标长什么样；
3. `../cli-sample/tools/`——6 个工具的 SDK 参考实现。

## 第 2 步：实现 TODO(1) write_file

打开 `tools/write_file_tool.py`，按注释实现 `_do_call`。完成后手动验证：

```bash
cd lesson4 && python -c "
from tools.write_file_tool import WriteFileTool
from tongagents.tools.tool_manager import ToolManager
import json, tempfile, pathlib
ToolManager.register_tool(WriteFileTool.name, WriteFileTool)
p = pathlib.Path(tempfile.mkdtemp()) / 'hello.txt'
out = ToolManager.get_tool_instance('write_file').call(json.dumps({'path': str(p), 'content': 'hi'}))
print(out, '| 磁盘上真实存在:', p.exists())
"
```

输出应有 `successfully`，且文件真的在磁盘上。

## 第 3-5 步：实现 TODO(2)-(5) 其余四个工具

`edit_file`（四处校验，任何一处失败都不得改动文件）、`bash`（shlex 分词 + subprocess，带超时）、`glob`（按文件名找）、`grep`（按内容找）。每个文件头部的提示已列出全部分支，行为对照 `../cli-sample/tools/` 同名工具。

## 第 6 步：实现 TODO(6) 工具注册

`tools/__init__.py` 的 `register_default_tools()`：逐个 `ToolManager.register_tool(cls.name, cls)`，已注册的跳过（幂等）。

## 第 7 步：跑自测（无 Key 无网络）

```bash
cd lesson4 && python check_homework.py
```

8 项全过即达标。test_07/08 是**框架级终验**：构造真实的 `StatelessReactAgent`，把它的 `llm` 换成 FakeLLM（脚本化假模型，接口对齐 SDK 的 `.request`），再走 `step()`——SDK 的真循环会解析 tool_call、从 ToolManager 找到你注册的工具、**真实执行**、把结果回填进下一轮请求。模型"说要写文件"，文件就必须真的出现在磁盘上——这就是"不得伪造工具调用"的可验证形式。

## 第 8 步：完成 TODO(7)(8) 接线并接真模型

`cli_file_sample.py` 里只剩两处：TODO(7) 用 `ReactAgentSetting` 构造 `StatelessReactAgent`（工具清单来自 `ToolManager.tool_classes`）；TODO(8) 从 `step()` 返回的 Action 列表里提取 `is_final_response=True` 的最终文本。运行：

```bash
cd lesson4 && python cli_file_sample.py
```

按"最终效果"里的三连场景验收：创建 → 编辑 → 搜索，完成后去磁盘确认文件真的变了。

## 验收标准

- `check_homework.py` 8 项全部通过（含 FakeLLM 驱动真实 SDK 循环的两项终验）；
- `python cli_file_sample.py` 真机完成"创建→编辑→搜索"连续场景，工具真实生效（文件真的变了）；
- 提交：`tools/` 与 `cli_file_sample.py` 的修改，以及一段真机对话记录。

## 延伸思考（选做）

- `step()` 返回的 actions 里除了最终 TextAction 还可能有什么？什么情况下一条回复会同时有文本和 tool_calls（看 `reference/stateless_react_agent.py` 的 `_process_blocking_model_message`）？
- 把 `write_file` 的 description 砍到只剩名字，真机上模型还会正确选它吗？体会 description 在 function calling 里的作用。
- 模型幻觉出一个没注册过的工具名，SDK 循环会怎样？读 `_tool_call` 的 not found 分支。
- 给 `bash` 加命令白名单（课件安全话题）：拒绝 `rm -rf` 类命令，怎么改既不误伤又不放行？
- `StatelessReactAgent` 为什么每轮都"失忆"？带上 memory 会怎样？（Lesson 6 的入口）
