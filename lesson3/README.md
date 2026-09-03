# Lesson 3 作业：把 CLI 改造成 Streaming 智能体

本节课不创建新的 Agent 项目。请继续使用课程提供的 `cli-sample/cli_sample.py`，在原有 CLI 上逐步增加流式输出能力。

## 预期结果

改造前，CLI 会等待模型生成完整答案，然后一次性打印：

```text
>>> 用三点解释什么是 Agent
  1. Agent 能理解目标……（等待几秒后整段出现）
```

改造后，模型生成一个 chunk，终端就立即显示一个 chunk：

```text
>>> 用三点解释什么是 Agent
  1. Agent 能理解目标……（文字持续出现）
```

完成后应满足：

- 使用 TongAgents 提供的真实 streaming，而不是拿到完整答案后自己逐字打印；
- 首个文本 chunk 到达后立即显示；
- 原来的文件工具仍然可用；
- 一轮回答结束后不会重复打印完整答案。

## 第 0 步：跑通原始 CLI

先不要改代码，确认基线可以运行：

```bash
cd cli-sample
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
uv sync
uv run python cli_sample.py
```

输入一个普通问题和一个文件问题，确认同步回答和工具调用都正常。

## 第 1 步：开启模型端 streaming

找到 `cli_sample.py` 中创建 `_llm_config` 的位置：

```python
_llm_config = ModelConfig(model_provider=ModelProvider.OPENAI_COMPATIBLE)
```

给 `ModelConfig` 增加 `stream=True`。这是让模型请求真正以流式返回的开关。

仅仅把字符串逐字 `print` 不算完成本步骤；如果仍然调用 `step()`，首字延迟也不会降低。

## 第 2 步：认识 TongAgents 的流事件

在 `tongagents.agents.llm_agent.defs` 的导入中，除了 `LLMInputEvent`，再导入：

```python
TextAction
TextActionType
```

一次模型响应通常包含以下事件：

```text
STREAM_START → STREAM_CONTENT × N → STREAM_FINISH
```

真正应该显示给用户的是 `STREAM_CONTENT` 的 `content`。开始和结束事件是控制信号，不是正文。

## 第 3 步：给 `CliSampleAgent` 增加流式方法

不要删掉原来的 `CliSampleAgent`，也不要另起一套脚手架。在类中新增一个方法，例如：

```python
def stream(self, event: Any) -> Iterator[str]:
    wrap = LLMInputEvent(input=[UserPromptMessage(str(event))])
    for action in self._agent.stream(wrap):
        # 判断它是不是 TextAction
        # 判断 type 是不是 STREAM_CONTENT
        # content 非空时 yield content
        ...
```

注意：

1. `LLMInputEvent.input` 继续传 `list[UserPromptMessage]`，不要破坏原 CLI 已验证的输入格式；
2. 必须持续消费迭代器直到自然结束；
3. ReAct 调用工具时，模型可能经历多轮响应，因此一轮用户请求中可能出现多组 START/CONTENT/FINISH；
4. 不输出 `reasoning_content`，避免把模型内部推理直接展示给用户。

## 第 4 步：改造 REPL 的打印逻辑

找到 `main()` 中原来的同步代码：

```python
response = agent.step(query)
print(f"  {response}")
```

把它改成遍历流式方法：

```python
print("  ", end="", flush=True)
for chunk in agent.stream(query):
    print(chunk, end="", flush=True)
print()
```

`end=""` 防止每个 chunk 单独换行，`flush=True` 保证 chunk 立刻出现在终端。循环结束后只调用一次 `print()` 补换行。

## 第 5 步：验证

运行：

```bash
cd cli-sample
uv run python cli_sample.py
```

依次检查：

1. 输入“写一段 300 字的 Agent 简介”，观察内容是否持续出现；
2. 输入“读取 README.md 的第一行”，确认工具调用后仍能输出最终回答；
3. 确认答案结尾没有重复出现完整文本；
4. 输入 `exit`，并分别测试 Ctrl+C、Ctrl+D；
5. 暂时把 `stream=True` 改回 `False`，比较首字等待时间，然后恢复。

## 验收标准

- 只修改 `cli-sample`，不创建另一套 Agent 工程；
- `ModelConfig(stream=True)` 和 `StatelessReactAgent.stream()` 缺一不可；
- 只打印非空的 `STREAM_CONTENT.content`；
- 使用 `flush=True`；
- 原有 6 个本地工具和退出命令均可继续使用。

