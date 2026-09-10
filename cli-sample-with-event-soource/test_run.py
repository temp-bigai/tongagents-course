#!/usr/bin/env python3
"""test_run.py - v2 集成测试 (Task #3468): 验证 AgentHandler 真的跑通.

放在 cli-sample-with-event-soource/test_run.py (跟 src/ 同级).

跑法:
    cd cli-sample-with-event-soource
    python3 test_run.py

期望:
- interval_seconds=2, max_count=3
- 大约 6-7 秒内完成
- AgentHandler 收到 3 个 Event, 每个 Event 触发 3 个 tool 调用 (bash + write_file + list_files)
- 日志文件 /tmp/es_agent_log.txt 含 3 条 [event] 记录
- handler.history 含 3 条 user + 9 条 tool 记录 (3 events × 3 tools)
- runtime 正常 stop, 不留僵尸线程
"""
from __future__ import annotations

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


def main() -> int:
    logger.info("===== test_run v2 开始 (AgentHandler + tools) =====")
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
        payload={"source": "test", "note": "v2 集成测试 AgentHandler"},
    )

    # AgentHandler (v2): 收到 event -> 包装 user query -> 调 mini agent + tools
    agent_handler = AgentHandler(
        name="test_agent",
        log_file=LOG_FILE,
        max_tool_calls=3,
    )

    # 同时挂 CliEventHandler 用于兼容性观察 (不影响主流程)
    cli_handler = CliEventHandler(name="cli_observer")

    runtime.add_source(timer_es)
    runtime.add_handler(agent_handler)
    runtime.add_handler(cli_handler)
    runtime.bind(timer_es, agent_handler)
    runtime.bind(timer_es, cli_handler)

    runtime.start()

    # 主循环: 等 runtime.is_running 自动变 False (所有 source 自然结束时 auto-stop)
    deadline = time.monotonic() + 15.0
    while runtime.is_running and time.monotonic() < deadline:
        time.sleep(0.2)

    # 兜底 stop (deadline 到了还没退)
    if runtime.is_running:
        logger.warning("Runtime 还没退, 兜底 stop")
        runtime.stop()

    elapsed = time.monotonic() - start_time
    logger.info("===== test_run v2 完成, elapsed=%.2fs =====", elapsed)

    # ==================================================================
    # 断言 1: 日志文件存在, 含 3 条 [event] 记录
    # ==================================================================
    assert os.path.exists(LOG_FILE), f"日志文件不存在: {LOG_FILE}"
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        log_content = f.read()
    event_count = log_content.count("[event]")
    logger.info("日志文件内容 (%d 条 [event]):", event_count)
    for line in log_content.splitlines():
        if line.strip():
            logger.info("  %s", line)
    assert event_count == 3, f"期望 3 条 [event], 实际 {event_count}"

    # ==================================================================
    # 断言 2: AgentHandler.history 含 3 user + 9 tool 记录
    # ==================================================================
    user_msgs = [h for h in agent_handler.history if h.get("role") == "user"]
    tool_msgs = [h for h in agent_handler.history if h.get("role") == "tool"]
    logger.info(
        "AgentHandler.history: %d user + %d tool = %d 总条数",
        len(user_msgs),
        len(tool_msgs),
        len(agent_handler.history),
    )
    assert len(user_msgs) == 3, f"期望 3 条 user, 实际 {len(user_msgs)}"
    assert len(tool_msgs) == 9, f"期望 9 条 tool (3 events × 3 tools), 实际 {len(tool_msgs)}"

    # ==================================================================
    # 断言 3: 每个 event 用了 bash + write_file + list_files
    # ==================================================================
    tools_used = [t.get("tool") for t in tool_msgs]
    bash_count = tools_used.count("bash")
    write_count = tools_used.count("write_file")
    list_count = tools_used.count("list_files")
    logger.info(
        "Tool 调用统计: bash=%d, write_file=%d, list_files=%d",
        bash_count,
        write_count,
        list_count,
    )
    assert bash_count == 3, f"期望 3 次 bash, 实际 {bash_count}"
    assert write_count == 3, f"期望 3 次 write_file, 实际 {write_count}"
    assert list_count == 3, f"期望 3 次 list_files, 实际 {list_count}"

    # ==================================================================
    # 断言 4: 耗时合理 (3 ticks @ 2s = ~6s, + 启动/收尾 1-4s)
    # ==================================================================
    assert 5.0 <= elapsed <= 12.0, f"期望 5-12 秒, 实际 {elapsed:.2f}"

    # ==================================================================
    # 断言 5: 线程都退了 (除主线程外)
    # ==================================================================
    alive = [t.name for t in threading.enumerate() if t != threading.main_thread()]
    logger.info("剩余非主线程: %s", alive)
    assert not alive, f"有线程没退出: {alive}"

    logger.info("✅ 全部断言通过 (AgentHandler + 4 tools + 日志写入)")
    logger.info("✅ 日志文件路径: %s", LOG_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())