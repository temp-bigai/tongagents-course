"""agent — ReAct 循环 (TODO 7, 全作业的核心).

《Building Effective Agents》的定义: "LLMs using tools based on
environmental feedback in a loop". 课件 2.4 节 (cell 17) 逐行讲过这个循环,
这里是它的正式版 —— main.py 的 REPL 每收到一句话就进来跑一圈:

    user 问题 ──┐
                ▼
        ┌── llm_chat(messages, tools=TOOLS) ◄─────────┐
        │                                            │ 回填: role=tool
        │ 无 tool_calls → 返回 msg.content            │ (tool_call_id + 结果)
        │                                            │
        └── 有 tool_calls → 逐个 call_tool() 执行 ───┘

对照: cli-sample 把这个循环整个委托给 SDK 的 StatelessReactAgent.step();
本作业要你亲手写它 —— 写完再看 cli_sample.py, 应该能指出 SDK 替你做了哪几步.
"""
from __future__ import annotations

from .llm import llm_chat
from .registry import TOOLS, call_tool


def agent_loop(
    question: str,
    system: str | None = None,
    max_turns: int = 8,
    llm=llm_chat,
    verbose: bool = False,
) -> tuple[str, list]:
    """TODO(7): 跑完整 ReAct 循环, 返回 (最终回答, 全部 messages).

    参数:
    - system:      system prompt (None 则不加)
    - max_turns:   最多循环轮数, 防止模型无限要工具
    - llm:         模型调用函数, 默认 llm_chat; check_homework 会注入 FakeLLM
    - verbose:     True 时逐轮打印 [turn N] 🔧 工具(参数) → 结果 (REPL 里开着)

    返回 (answer, messages):
    - messages 是完整对话轨迹, 自测靠它验证"工具结果回填"是否正确

    实现提示 (对照课件 cell 17, 四步):
        messages = []
        1) system 非空则 append {"role": "system", ...}; append user 问题
        2) for turn in range(1, max_turns + 1):
               msg = llm(messages=messages, tools=TOOLS)
        3)     msg.tool_calls 为空 -> return (msg.content, messages)   # 最终回答
        4)     否则 messages.append(msg)  # assistant 消息必须先回传!
               逐个 tc: result = call_tool(tc.function.name, tc.function.arguments)
               messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        循环耗尽: return ("(达到最大轮数, 停止)", messages)
    """
    # TODO(7): 删除下面这行占位, 按上面四步实现 (messages 初始化已给)
    messages: list = []
    raise NotImplementedError("Lesson 4 TODO(7): 实现 agent_loop")
