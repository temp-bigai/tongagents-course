#!/usr/bin/env python3
"""test_run.py - v3 集成测试 (Task #3469): 验证 AgentHandler 真调 LLM + tool.

放在 cli-sample-with-event-soource/test_run.py (跟 src/ 同级).

跑法:
    cd cli-sample-with-event-soource
    python3 test_run.py                # 默认: 有 OPENAI_API_KEY + OPENAI_MODEL 走真 LLM, 否则 mock
    python3 test_run.py --mock         # 强制走 mock 路径 (不管 env)
    python3 test_run.py --real         # 强制走真 LLM 路径 (没 env 会退出码 2)

期望:
- 真 LLM 路径: AgentHandler._llm_available=True, _agent is not None
- mock 路径: 3 ticks × 3 tools = 9 tool records (跟 v2 兼容)
- 真 LLM 路径: history 含 N user + N×M assistant actions (M 由 LLM 决定, 通常 2)
- 日志文件 /tmp/es_agent_log.txt 含 3 条 [es-agent-event] 记录 (mock + 真 LLM 都写)
- runtime 正常 stop, 不留僵尸线程
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

# 让 import 能找到 src/event_source 和 src/handlers
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from event_source import EventSourceRuntime, TimerEventSource  # noqa: E402
from handlers import AgentHandler, CliEventHandler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_run")


LOG_FILE = "/tmp/es_agent_log.txt"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="test_run.py v3 (Task #3469)")
    p.add_argument(
        "--mock",
        action="store_true",
        help="强制走 mock 路径 (不管 OPENAI_API_KEY / OPENAI_MODEL)",
    )
    p.add_argument(
        "--real",
        action="store_true",
        help="强制走真 LLM 路径 (没 env 会失败退出 2)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    logger.info("===== test_run v3 开始 (AgentHandler + 真 LLM 路径) =====")
    logger.info("OPENAI_API_KEY=%s", "✓" if os.environ.get("OPENAI_API_KEY") else "✗")
    logger.info("OPENAI_MODEL=%s", os.environ.get("OPENAI_MODEL") or "✗")
    start_time = time.monotonic()

    # 清空旧日志, 避免上次测试残留
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
        logger.info("清空旧日志: %s", LOG_FILE)

    runtime = EventSourceRuntime()
    timer_es = TimerEventSource(
        name="test_timer",
        interval_seconds=2,
        max_count=3,
        event_type="timer.tick",
        payload={"source": "test", "note": "v3 集成测试 (真 LLM)"},
    )

    # AgentHandler (v3): 收到 event -> 包装 user query -> 调真 LLM (或 mock fallback)
    agent_handler = AgentHandler(
        name="test_agent",
        log_file=LOG_FILE,
        max_tool_calls=3,
    )

    # 根据 args 强制决定走哪条路径
    if args.mock:
        logger.info("🔧 强制 mock 路径 (--mock)")
        agent_handler._llm_available = False
        agent_handler._agent = None
    elif args.real:
        if not agent_handler._llm_available:
            logger.error(
                "❌ --real 但真 LLM 不可用 (缺 OPENAI_API_KEY / OPENAI_MODEL / tongagents SDK)"
            )
            return 2
        logger.info("🔧 强制真 LLM 路径 (--real)")

    path_kind = "真 LLM" if agent_handler._llm_available else "mock"
    logger.info("走 %s 路径", path_kind)

    # 同时挂 CliEventHandler 用于兼容性观察 (不影响主流程)
    cli_handler = CliEventHandler(name="cli_observer")

    runtime.add_source(timer_es)
    runtime.add_handler(agent_handler)
    runtime.add_handler(cli_handler)
    runtime.bind(timer_es, agent_handler)
    runtime.bind(timer_es, cli_handler)

    runtime.start()

    # 真 LLM 路径每个 tick 多花 5-15s (API 往返 + tool 执行),
    # 给 60s 上限, mock 路径大约 6-7s 完成
    deadline_sec = 70.0 if agent_handler._llm_available else 15.0
    deadline = time.monotonic() + deadline_sec
    while runtime.is_running and time.monotonic() < deadline:
        time.sleep(0.2)

    # 兜底 stop (deadline 到了还没退)
    if runtime.is_running:
        logger.warning("Runtime 还没退, 兜底 stop")
        runtime.stop()

    elapsed = time.monotonic() - start_time
    logger.info("===== test_run v3 完成, elapsed=%.2fs, path=%s =====", elapsed, path_kind)

    # ==================================================================
    # 断言 1: 日志文件存在, 含 3 条 [es-agent-event] 记录
    # (真 LLM + mock 都写日志, 因为 _call_real_llm_loop 也写 [es-agent-event] 行)
    # ==================================================================
    import re

    assert os.path.exists(LOG_FILE), f"日志文件不存在: {LOG_FILE}"
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        log_lines = f.readlines()
    # 严格匹配我们自己的日志格式: "[ISO timestamp] [es-agent-event] ..."
    # 用独特 marker [es-agent-event] 避免跟 LLM 写入的 [event] 字符串混淆
    # 兼容 ISO8601 (T 分隔) 和 LLM 写入的 space 分隔
    # NOTE: 用完整文件内容 (而非按行) 计数, 因为 LLM 可能不写 newline,
    #       导致它 write_file 的内容跟我们的 [es-agent-event] 行拼在一起.
    event_re = re.compile(r"\[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\] \[es-agent-event\]")
    log_content = "".join(log_lines)
    event_count = len(event_re.findall(log_content))
    logger.info("日志文件内容 (%d 条 [es-agent-event]):", event_count)
    for line in log_lines:
        if line.strip():
            logger.info("  %s", line.rstrip())
    assert event_count == 3, f"期望 3 条 [es-agent-event], 实际 {event_count}"

    # ==================================================================
    # 断言 2: AgentHandler.history 含 3 条 user
    # (mock 路径有 9 条 tool; 真 LLM 路径由 SDK 返回 actions 决定, 通常每 tick 1-3 个 assistant action)
    # ==================================================================
    user_msgs = [h for h in agent_handler.history if h.get("role") == "user"]
    logger.info(
        "AgentHandler.history: %d user + %d 其他 = %d 总条数",
        len(user_msgs),
        len(agent_handler.history) - len(user_msgs),
        len(agent_handler.history),
    )
    assert len(user_msgs) == 3, f"期望 3 条 user, 实际 {len(user_msgs)}"

    if agent_handler._llm_available:
        # 真 LLM 路径: 每 tick 至少 1 个 final assistant action
        final_msgs = [
            h
            for h in agent_handler.history
            if h.get("role") == "assistant" and h.get("is_final_response")
        ]
        logger.info("真 LLM 路径 final action 数: %d", len(final_msgs))
        assert len(final_msgs) >= 3, (
            f"真 LLM 路径期望至少 3 条 final action, 实际 {len(final_msgs)}"
        )

        # 真 LLM 路径不应有 mock 路径专属的 tool role 记录
        tool_msgs = [h for h in agent_handler.history if h.get("role") == "tool"]
        logger.info("真 LLM 路径 tool role 记录数: %d (应为 0, 由 SDK 内部处理)", len(tool_msgs))
        assert len(tool_msgs) == 0, (
            f"真 LLM 路径不应有 tool role 记录, 实际 {len(tool_msgs)}"
        )
    else:
        # mock 路径: 3 events × 3 tools = 9 条 tool
        tool_msgs = [h for h in agent_handler.history if h.get("role") == "tool"]
        assert len(tool_msgs) == 9, f"mock 路径期望 9 条 tool (3 events × 3 tools), 实际 {len(tool_msgs)}"

        # mock 路径: bash + write_file + list_files 各 3 次
        tools_used = [t.get("tool") for t in tool_msgs]
        bash_count = tools_used.count("bash")
        write_count = tools_used.count("write_file")
        list_count = tools_used.count("list_files")
        logger.info(
            "Mock tool 调用统计: bash=%d, write_file=%d, list_files=%d",
            bash_count,
            write_count,
            list_count,
        )
        assert bash_count == 3, f"期望 3 次 bash, 实际 {bash_count}"
        assert write_count == 3, f"期望 3 次 write_file, 实际 {write_count}"
        assert list_count == 3, f"期望 3 次 list_files, 实际 {list_count}"

    # ==================================================================
    # 断言 3: 耗时合理
    # - mock 路径: 3 ticks @ 2s = ~6s, + 启动/收尾 1-4s → 5-12s
    # - 真 LLM 路径: 3 ticks × (API 往返 3-10s + tool 0-3s) = 9-40s
    # ==================================================================
    if agent_handler._llm_available:
        assert elapsed <= 70.0, f"真 LLM 路径耗时 > 70s: {elapsed:.2f}"
    else:
        assert 5.0 <= elapsed <= 12.0, f"mock 路径期望 5-12 秒, 实际 {elapsed:.2f}"

    # ==================================================================
    # 断言 4: 我们的 app 线程都退了 (除主线程外, 容许 SDK 自己的后台线程如 fsspecIO)
    # ==================================================================
    # tongagents SDK 会启动 fsspecIO 后台线程 (用于文件 IO 池), 这是 SDK 内部的,
    # 不属于我们 app 的线程泄漏. 我们的 app 只跑 EventSourceRuntime 的 dispatcher 线程,
    # 它在 runtime.stop() 时应该退出.
    _SDK_THREADS = {"fsspecIO"}  # 容许的 SDK 自带后台线程名
    alive = [
        t.name
        for t in threading.enumerate()
        if t != threading.main_thread() and t.name not in _SDK_THREADS
    ]
    logger.info("剩余 app 线程 (排除 SDK 自带): %s", alive)
    assert not alive, f"有 app 线程未退: {alive}"

    logger.info("✅ 全部断言通过 (AgentHandler v3 + %s 路径)", path_kind)
    logger.info("✅ 日志文件路径: %s", LOG_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())