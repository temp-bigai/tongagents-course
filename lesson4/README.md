# Lesson 4: Tool、MCP、CLI 与 Skill

本课使用一个可执行 Jupyter Notebook，对比四种常被混用的 Agent 扩展方式：

- **Tool**：模型可选择调用的、带结构化参数的函数。
- **MCP**：客户端发现和调用远程/本地能力的开放协议。
- **CLI**：人或程序通过进程参数、标准输入输出调用应用的接口。
- **Skill**：供 Agent 按需加载的可复用说明、脚本与资源包；它不是新的传输协议。

Notebook 默认使用确定性的本地数据，所以没有 API Key 也能从头运行。最后一节提供 OpenAI-compatible 的真实模型调用，配置后再执行即可。

## 安装与启动

需要先安装 [uv](https://docs.astral.sh/uv/)。然后在仓库根目录执行：

```bash
cd lesson4
uv sync
uv run jupyter lab lesson4_tools_mcp_cli_skill.ipynb
```

也可以启动经典 Notebook 界面：

```bash
uv run jupyter notebook lesson4_tools_mcp_cli_skill.ipynb
```

## 配置 OpenAI-compatible 模型（可选）

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

对于其他兼容服务，把 `OPENAI_BASE_URL` 和 `OPENAI_MODEL` 换成服务商给出的值。兼容服务对 tool calling 的支持程度可能不同；本地 Tool、CLI、MCP、Skill 示例不受影响。

## 独立验证

```bash
uv run pytest -q
uv run python demo_cli.py weather --city Shanghai
uv run python -c "from tool_demo import dispatch_tool; print(dispatch_tool('calculate', {'expression': '6 * 7'}))"
uv run jupyter nbconvert --to notebook --execute lesson4_tools_mcp_cli_skill.ipynb --output /tmp/lesson4-executed.ipynb
```

## 文件说明

```text
lesson4/
├── lesson4_tools_mcp_cli_skill.ipynb  # 主课件
├── tool_demo.py                       # Tool schema、实现与安全分发
├── mcp_server.py                      # FastMCP stdio server
├── demo_cli.py                        # argparse CLI
├── openai_tool_agent.py               # 可选的真实模型 tool-calling loop
├── .agents/skills/course-summary/
│   └── SKILL.md                       # repo-local Skill 示例
├── tests/test_demos.py
├── .env.example
└── pyproject.toml
```

## 参考资料

- [Claude Cookbooks: Tool use](https://github.com/anthropics/claude-cookbooks/tree/main/tool_use)
- [Model Context Protocol 文档](https://modelcontextprotocol.io/docs/getting-started/intro)
- [OpenAI 官方文档：Build skills](https://developers.openai.com/codex/skills/)
