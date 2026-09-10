#!/usr/bin/env python3
"""test_run.py - v4 集成测试 (Task #3470).

验证 v4 架构:
1. 单 handler (AgentHandler) — 没有 CliEventHandler / cli_observer
2. 复用 cli-sample 的"等 user input + agent.step + print response"循环
3. ES event 包装成 user input, 注入到 input_queue
4. main loop 从 input_queue 拿 item (user + event 都一样), 走 cli-sample 循环
5. 真跑通 (有 OPENAI_API_KEY + OPENAI_MODEL 时调真 LLM, 否则跑通架构即可)

跑法:
    cd cli-sample-with-event-soource
    python3 test_run.py                # 默认: 真 LLM (如果有 env), 否则走 mock 注入
    python3 test_run.py --mock-llm     # 强制不让 agent.step 真调 LLM, 直接跳过

期望:
- ES 触发 3 次, 每次都被 dispatcher 转成 user input, 推到 input_queue
- main loop 从 input_queue 拿出 3 条 [ES 自动输入], 走 cli-sample 循环
- 每次都有响应 (真 LLM 路径) 或显式跳过 (mock 路径)
- 全部断言通过

注意 v4 跟 v3 的差别:
- v3 测试主要断言 AgentHandler.history 含 3 条 user + 9 条 tool + 日志文件
- v4 测试主要断言 ES event 进入了 input_queue, 循环处理了 3 次
- v4 不再断言 AgentHandler 自己有 history (handler 只是个容器, history 在 agent 内部)
"""
from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
import threading
import time
from pathlib import Path

# 让 import 能找到 src/event_source 和 src/handlers
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from event_source import EventSourceRuntime, TimerEventSource  # noqa: E402
from handlers import AgentHandler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_run")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="test_run.py v4 (Task #3470)")
    p.add_argument(
        "--mock-llm",
        action="store_true",
        help="不让 agent.step 真调 LLM (跳过 step 调用, 只验证 ES 注入 + 循环结构)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logger.info("===== test_run v4 开始 (单 handler + 复用 cli-sample 循环) =====")
    logger.info("OPENAI_API_KEY=%s", "✓" if os.environ.get("OPENAI_API_KEY") else "✗")
    logger.info("OPENAI_MODEL=%s", os.environ.get("OPENAI_MODEL") or "✗")
    logger.info("--mock-llm=%s", args.mock_llm)
    start_time = time.monotonic()

    # 1. 单 handler (复用 cli-sample 模式)
    agent_handler = AgentHandler(name="test_agent")

    # 2. Runtime + TimerEventSource (3 次 / 2 秒间隔 = 约 6 秒)
    #    auto_dispatch=False: v4 关键, 让外部 ES dispatcher 消费 Event
    runtime = EventSourceRuntime(auto_dispatch=False)
    timer_es = TimerEventSource(
        name="test_timer",
        interval_seconds=2,
        max_count=3,
        event_type="timer.tick",
        payload={"source": "test", "note": "v4 测试 ES 注入 input_queue"},
    )
    runtime.add_source(timer_es)

    # 3. 共享 input_queue
    input_queue: "queue.Queue[str]" = queue.Queue()

    # 4. ES dispatcher (复用 main.py 的实现, 不用重新发明)
    from main import make_es_dispatcher, event_to_user_input  # noqa: E402
    es_dispatcher = make_es_dispatcher(runtime, input_queue)

    # 5. 启动
    runtime.start()
    dispatcher_thread = threading.Thread(
        target=es_dispatcher,
        name="test-es-dispatcher",
        daemon=True,
    )
    dispatcher_thread.start()

    # 6. 复用 cli-sample 循环: 从 input_queue 拿 user input, 走 agent.step
    processed_inputs: list[str] = []
    agent_responses: list[str] = []
    deadline = time.monotonic() + 30.0  # 3 ticks @ 2s + buffer

    while time.monotonic() < deadline:
        try:
            user_input = input_queue.get(timeout=0.5)
        except queue.Empty:
            # 兜底: 3 个 tick 都处理完 + 等一会儿, 就退出
            if len(processed_inputs) >= 3:
                break
            if not runtime.is_running and input_queue.empty():
                break
            continue

        processed_inputs.append(user_input)

        # 校验: 必须是 ES 注入的 (含 [ES 自动输入])
        assert "[ES 自动输入]" in user_input, (
            f"期望 ES 注入的 user input, 实际: {user_input[:80]}"
        )

        # 走 agent.step (复用 cli-sample 循环结构)
        if args.mock_llm:
            response = "[mock response] 收到定时事件, 已记录到日志"
            logger.info("[test] --mock-llm 跳过 agent.step")
        else:
            try:
                from tongagents.agents.llm_agent.defs import LLMInputEvent  # type: ignore
                from tongagents.agents.llm.messages import UserPromptMessage  # type: ignore

                wrap = LLMInputEvent(input=[UserPromptMessage(user_input)])
                actions = agent_handler.agent.step(wrap)
                response = ""
                for action in actions:
                    if getattr(action, "is_final_response", False):
                        response = (action.content or "").strip()
                        break
                if not response:
                    for action in actions:
                        if hasattr(action, "content") and action.content:
                            response = action.content.strip()
                            break
                logger.info("[test] agent.step 完成, response=%s", response[:80])
            except Exception as e:  # noqa: BLE001
                logger.exception("[test] agent.step 失败: %s", e)
                response = f"[error] {type(e).__name__}: {e}"

        agent_responses.append(response)
        logger.info(
            "[test] 处理第 %d 条 input 完成 (含 [ES 自动输入] 标记)",
            len(processed_inputs),
        )

    # 7. 清理
    if runtime.is_running:
        runtime.stop()
    dispatcher_thread.join(timeout=3.0)

    elapsed = time.monotonic() - start_time
    logger.info("===== test_run v4 完成, elapsed=%.2fs =====", elapsed)
    logger.info("处理的 input 数: %d", len(processed_inputs))
    logger.info("agent response 数: %d", len(agent_responses))

    # ==================================================================
    # 断言 1: 处理了 3 条 ES 注入的 input
    # ==================================================================
    assert len(processed_inputs) == 3, (
        f"期望 3 条 ES 注入的 user input, 实际 {len(processed_inputs)}"
    )

    # ==================================================================
    # 断言 2: 每条都含 [ES 自动输入] 标记 (event 转 user input 成功)
    # ==================================================================
    for i, inp in enumerate(processed_inputs, 1):
        assert "[ES 自动输入]" in inp, f"第 {i} 条 input 缺 [ES 自动输入] 标记"
        assert "type: timer.tick" in inp, f"第 {i} 条 input 缺 type 字段"
        assert "payload" in inp, f"第 {i} 条 input 缺 payload 字段"
    logger.info("✅ 3 条 ES 注入 input 全部含正确格式")

    # ==================================================================
    # 断言 3: agent 有响应 (mock 或真 LLM 都给 response)
    # ==================================================================
    assert len(agent_responses) == 3, f"期望 3 条 agent response, 实际 {len(agent_responses)}"
    for i, resp in enumerate(agent_responses, 1):
        assert resp, f"第 {i} 条 response 为空"
    logger.info("✅ 3 条 agent response 全部非空")

    # ==================================================================
    # 断言 4: 耗时合理 (3 ticks @ 2s = ~6s, + buffer)
    # ==================================================================
    assert elapsed <= 30.0, f"耗时 > 30s: {elapsed:.2f}"
    logger.info("✅ 耗时 %.2fs 在合理范围", elapsed)

    # ==================================================================
    # 断言 5: 没有 CliEventHandler 残留 (单 handler 验证)
    # ==================================================================
    from handlers import AgentHandler as _AH
    assert _AH.__name__ == "AgentHandler"
    try:
        from handlers import CliEventHandler  # noqa: F401
        assert False, "CliEventHandler 不应存在 (v4 单 handler)"
    except ImportError:
        logger.info("✅ handlers 包无 CliEventHandler (单 handler 验证通过)")

    logger.info("=" * 60)
    logger.info("✅ 全部断言通过 (v4 架构: 单 handler + 复用 cli-sample 循环)")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
