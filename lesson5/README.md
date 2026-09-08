# Lesson 5 作业：给 CLI 增加 ReAct 论文检索与综述能力

本节课继续修改同一份 `cli-sample/cli_sample.py`。CLI 已经使用 TongAgents 的 `StatelessReactAgent`：SDK 内部会自动完成“模型决定调用工具 → 执行工具 → 把观察结果交还模型 → 继续生成”的 ReAct 循环。本次作业要做的是增加一个 arXiv 工具，并用 prompt 把它约束成论文综述 Agent。

## 预期结果

运行原来的 CLI：

```bash
cd cli-sample
uv run python cli_sample.py
```

输入：

```text
>>> 检索 LLM Agent memory 相关论文，并基于摘要生成一篇中文综述
```

Agent 应该先调用 `search_arxiv`，再输出包含以下部分的 Markdown 综述：

- 检索范围与证据说明；
- 研究脉络；
- 方法分类；
- 代表论文比较；
- 共同局限与未来方向；
- 带 arXiv 链接的参考论文。

如果网络错误或没有结果，Agent 应如实说明，不能凭模型记忆编造论文。

## 第 0 步：确认起点

本作业的起点仍然是：

```text
cli-sample/
├── cli_sample.py
└── tools/
    ├── __init__.py
    ├── read_file_tool.py
    └── ...
```

如果你已经完成 Streaming 作业，保留相关修改即可。本节新增工具和 prompt，不需要重写 REPL。

## 第 1 步：理解现有工具接入方式

阅读：

- `tools/read_file_tool.py`：一个 TongAgents `Tool` 如何声明名称、描述、参数和 `_do_call()`；
- `tools/__init__.py`：工具类如何加入 `_DEFAULT_TOOL_CLASSES`，再注册进 `ToolManager`；
- `cli_sample.py`：`tool_identifier_list` 如何把已注册工具交给 `StatelessReactAgent`。

接下来完全沿用这条链路增加第 7 个工具，不另写 Agent 框架。

## 第 2 步：创建 arXiv 工具文件

在 `cli-sample/tools/` 下新建 `arxiv_search_tool.py`，实现：

```python
class ArxivSearchTool(Tool):
    name = "search_arxiv"
    description = "按关键词检索 arXiv 论文，返回标题、作者、日期、摘要和链接"
    parameters = ToolParameters(...)

    def _do_call(self, params: dict, **kwargs) -> str:
        ...
```

参数包含：

- `query: string`：英文关键词；
- `max_results: integer`：默认 5，并在代码中强制限制到 1–10。

清晰的工具描述很重要，因为模型会根据名称、描述和参数 Schema 决定何时以及如何调用工具。

## 第 3 步：请求 arXiv API

使用 Python 标准库即可，不必增加第三方依赖：

```python
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
```

请求地址为：

```text
https://export.arxiv.org/api/query
```

查询参数至少包含：

```python
{
    "search_query": f"all:{query}",
    "start": 0,
    "max_results": max_results,
    "sortBy": "submittedDate",
    "sortOrder": "descending",
}
```

请求时设置：

- 20 秒左右的 timeout；
- 能标识课程程序的 `User-Agent`；
- `Accept: application/atom+xml`。

网络错误不要直接抛出长 traceback。将错误整理成 JSON 字符串返回，让 Agent 能读懂并决定如何回答用户。

## 第 4 步：解析 Atom XML

arXiv 返回 Atom XML。需要处理两个 namespace：

```python
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
```

遍历每个 `entry`，提取：

- `title`
- `authors`
- `published`
- `summary`
- `primary_category`
- `arxiv_url`
- `pdf_url`

建议用 `re.sub(r"\s+", " ", text).strip()` 清理标题和摘要中的换行与多余空格。最终用 `json.dumps(..., ensure_ascii=False)` 返回结构化结果，并明确注明“只读取了元数据和作者摘要，没有读取 PDF 全文”。

## 第 5 步：注册工具

修改 `cli-sample/tools/__init__.py`：

1. 导入 `ArxivSearchTool`；
2. 把它加入 `_DEFAULT_TOOL_CLASSES`；
3. 把它加入 `__all__`。

运行下面的命令检查注册是否成功：

```bash
cd cli-sample
uv run python -c "from tools import register_default_tools; from tongagents.tools.tool_manager import ToolManager; register_default_tools(); print(ToolManager.tool_classes.keys())"
```

输出中应该包含 `search_arxiv`。

## 第 6 步：把 CLI 约束成论文综述 Agent

回到 `cli_sample.py`，修改 `_SYSTEM_PROMPT`。至少加入以下规则：

1. 收到论文综述请求后，必须先调用 `search_arxiv`；
2. 中文主题先提炼成简洁的英文检索词；
3. 主题过宽时可以换关键词检索 2–3 次；
4. 只能引用工具结果中出现的论文，标题和链接必须一致；
5. 工具仅返回摘要，最终输出必须声明证据边界；
6. 使用中文 Markdown 输出“范围、脉络、分类、比较、局限、未来方向、参考论文”；
7. 不向用户输出隐藏推理过程或 Thought/Action/Observation 标签。

为了减少无关工具干扰，可以把：

```python
tool_identifier_list=list(ToolManager.tool_classes.keys())
```

改成：

```python
tool_identifier_list=["search_arxiv"]
```

这样保留原有工具代码，但本节的 Agent 只看到论文检索工具。

## 第 7 步：运行完整 ReAct 链路

```bash
cd cli-sample
uv run python cli_sample.py
```

建议依次测试：

```text
检索 2023 年以来 LLM Agent memory 的论文并生成综述
检索 retrieval-augmented generation 的代表工作，比较主要方法
检索 multi-agent collaboration for LLMs，指出当前评测的局限
```

观察一次请求是否经过：

```text
用户主题 → 模型选择 search_arxiv → 工具返回 Atom 解析结果
        → 模型基于观察继续推理 → 输出有引用的综述
```

## 验收标准

- 作业是在原 `cli-sample` 上增量完成的；
- `search_arxiv` 是 TongAgents `Tool`，不是在 REPL 中硬编码关键词判断；
- Agent 至少实际调用一次工具后才写事实性综述；
- `max_results` 被限制为 1–10，请求有 timeout 和 User-Agent；
- 综述中引用的标题与链接都能在工具结果中找到；
- 断网、空结果和 XML 错误都有可理解的反馈；
- 不把模型隐藏推理过程作为答案展示。

