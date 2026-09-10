"""v5 test: queue + event 统一 input.

测试目标:
    1. 注入 1 个 user input (走 stdin reader 模式: 直接 runtime.add_user_input)
    2. 启动 timer (3 次事件, 每次 2 秒间隔)
    3. 从 runtime.input_queue 收集所有 items
    4. 断言:
       - 至少 4 items (1 user + 3 es events)
       - 至少有 1 个 origin='stdin' (user input)
       - 至少有 3 个 origin='es_event:xxx' (ES events)
       - FIFO 顺序: user input 在最前 (因为先注入)

v5 关键验证:
    - Runtime.input_queue 是统一来源 (user + event 一个 queue)
    - handler.handle(event, runtime) 把 event 包装推 runtime.input_queue
    - 没有独立的 es_dispatcher 线程
"""
import logging
import sys
import time
from pathlib import Path

# 把 src/ 加入 sys.path, 让 import event_source/handlers 能找到
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
logger = logging.getLogger("v5-test")


def run_test() -> int:
    print("\n=== v5 EventSource queue + event test ===\n")

    # 1. 构造 runtime (v5 单 queue)
    runtime = EventSourceRuntime()

    # 2. 注册 handler + source
    agent_handler = AgentHandler(name="test_agent")
    timer_es = TimerEventSource(
        name="test_timer",
        interval_seconds=2,
        max_count=3,
        event_type="timer.tick",
        payload={"source": "test"},
    )
    runtime.add_source(timer_es)
    runtime.add_handler(agent_handler)
    runtime.bind(timer_es, agent_handler)

    # 3. 注入 1 个 user input (模拟 stdin reader 推送)
    runtime.add_user_input("hi from test user", source_tag="stdin")

    # 4. 启动 timer
    runtime.start()
    print("[test] runtime started, timer firing every 2s, max_count=3\n")

    # 5. 跑 8 秒, 收集 input_queue 内容
    processed = []
    start = time.time()
    deadline = start + 8.0  # 8 秒足够 1 user + 3 es events 完成
    while time.time() < deadline:
        item = runtime.get_input(timeout=0.5)
        if item:
            processed.append(item)
            origin = item["origin"]
            content = item["content"]
            print(
                f"[test] got item #{len(processed)} origin={origin!r} "
                f"content={content[:80]!r}"
            )

    runtime.stop()
    print()

    # 6. 断言
    print("[test] === assertions ===")

    # 至少 4 items (1 user + 3 es events, 留 buffer)
    assert len(processed) >= 4, (
        f"❌ 期望 ≥4 items (1 user + 3 es), 实际 {len(processed)}"
    )
    print(f"  ✅ total items: {len(processed)} (>= 4)")

    # 至少 1 个 stdin
    user_items = [p for p in processed if p["origin"] == "stdin"]
    assert len(user_items) >= 1, (
        f"❌ 期望 ≥1 stdin item, 实际 {len(user_items)}"
    )
    print(f"  ✅ stdin items: {len(user_items)} (>= 1)")

    # 至少 3 个 es_event
    es_items = [p for p in processed if p["origin"].startswith("es_event:")]
    assert len(es_items) >= 3, (
        f"❌ 期望 ≥3 es_event items, 实际 {len(es_items)}"
    )
    print(f"  ✅ es_event items: {len(es_items)} (>= 3)")

    # FIFO: 第一个 item 应该是 user input (先注入)
    assert processed[0]["origin"] == "stdin", (
        f"❌ FIFO 失败: 第一个 item origin={processed[0]['origin']!r}, "
        f"期望 'stdin'"
    )
    print(f"  ✅ FIFO: first item origin={processed[0]['origin']!r}")

    # Runtime 状态
    assert len(runtime.event_history) >= 3, (
        f"❌ runtime.event_history 期望 ≥3, 实际 {len(runtime.event_history)}"
    )
    print(f"  ✅ runtime.event_history: {len(runtime.event_history)} (>= 3)")

    assert len(runtime.user_input_history) >= 4, (
        f"❌ runtime.user_input_history 期望 ≥4, 实际 {len(runtime.user_input_history)}"
    )
    print(
        f"  ✅ runtime.user_input_history: {len(runtime.user_input_history)} (>= 4)"
    )

    print("\n🎉 全部断言通过!")
    print(f"   total={len(processed)}, "
          f"stdin={len(user_items)}, es_event={len(es_items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_test())