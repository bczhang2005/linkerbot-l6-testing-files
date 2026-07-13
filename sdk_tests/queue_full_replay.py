"""
queue_full_replay.py

【测试目的】
  故意复现 queue.Full：不 stop 默认轮询，循环 get_blocking + 间歇发运动指令，直到队列堵死。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电
  · ⚠️ 本脚本为问题复现用，正常运行其他脚本前请先 stop_polling

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python queue_full_replay.py
  3. 等待终端打印 queue.Full 或「queue.Full 复现成功！」

【预期结果】
  · 预检通过后，运行一段时间因队列满而报错退出
  · queue.Full 可能出现在主线程，也可能出现在 L6-Polling-* 后台线程
  · 仅确认 queue.Full 时打印「queue.Full 复现成功！」
  · 手未上电/连错手 → 预检失败或超时，不会误报复现成功

【实际结果】
  （测试后在此填写）

【说明】
  默认角度 60Hz + 力传感器 30Hz 轮询与频繁阻塞读叠加易堵队列；
  无力传感器机型更易复现。正常开发应始终 stop 默认轮询。
  本脚本通过 threading.excepthook 捕获后台轮询线程中的 queue.Full。
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from dataclasses import dataclass

from linkerbot import L6
from linkerbot.exceptions import TimeoutError as LinkerTimeoutError

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "right"
VERIFY_TIMEOUT_MS = 3000


def is_queue_full_error(exc: BaseException) -> bool:
    if isinstance(exc, queue.Full):
        return True
    name = type(exc).__name__
    msg = str(exc).lower()
    return name == "Full" or "queue.full" in msg or "queue full" in msg


@dataclass(frozen=True)
class BackgroundQueueFullHit:
    thread_name: str
    exc_type: str
    message: str


class PollingThreadMonitor:
    """捕获 L6 后台轮询线程里未处理的 queue.Full。"""

    def __init__(self) -> None:
        self.queue_full_hits: list[BackgroundQueueFullHit] = []
        self.other_thread_errors: list[tuple[str, str, str]] = []
        self._previous_hook = threading.excepthook

    def install(self) -> None:
        threading.excepthook = self._on_thread_exception

    def restore(self) -> None:
        threading.excepthook = self._previous_hook

    def _on_thread_exception(self, args: threading.ExceptHookArgs) -> None:
        exc = args.exc_value
        thread_name = args.thread.name if args.thread is not None else "<unknown>"

        if exc is not None:
            if is_queue_full_error(exc):
                self.queue_full_hits.append(
                    BackgroundQueueFullHit(
                        thread_name=thread_name,
                        exc_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
            else:
                self.other_thread_errors.append(
                    (thread_name, type(exc).__name__, str(exc))
                )

        if self._previous_hook is not None:
            self._previous_hook(args)

    @property
    def detected_queue_full(self) -> bool:
        return bool(self.queue_full_hits)


def find_dead_polling_threads(hand: L6) -> list[str]:
    """轮询线程异常退出后 is_alive() 会变 False，用作辅助信号。"""
    dead: list[str] = []
    polling_threads = getattr(hand, "_polling_threads", {})
    for source_name, thread in polling_threads.items():
        if not thread.is_alive():
            dead.append(f"L6-Polling-{source_name}")
    return dead


def print_conclusion(
    *,
    count: int,
    successful_reads: int,
    elapsed: float,
    queue_full: bool,
    source: str,
    successful_reads_required: bool = True,
    error: BaseException | None = None,
    background_hits: list[BackgroundQueueFullHit] | None = None,
    dead_threads: list[str] | None = None,
) -> None:
    print(f"\n运行时间: {elapsed}秒，主循环次数: {count}，成功读角: {successful_reads}次")

    if background_hits:
        for hit in background_hits:
            print(f"[后台线程] {hit.thread_name}: {hit.exc_type}: {hit.message}")

    if dead_threads:
        print(f"[辅助信号] 已停止的轮询线程: {', '.join(dead_threads)}")

    if error is not None:
        print(f"第{count}次主线程出错: {type(error).__name__}: {error}")

    if queue_full:
        if successful_reads > 0 or not successful_reads_required:
            print(f"✅ queue.Full 复现成功！（检测来源: {source}）")
        else:
            print("⚠️  出现 queue.Full，但尚未成功读角，无法确认为有效复现")
        return

    if isinstance(error, LinkerTimeoutError) or successful_reads == 0:
        print("❌ 读角超时或从未读成功：灵巧手未连接、已断开或 HAND_SIDE 错误")
        print("   （这不是 queue.Full 复现，请检查硬件连接）")
    elif error is not None:
        print(f"❌ 未预期的错误（非 queue.Full 复现）: {type(error).__name__}: {error}")
    else:
        print("ℹ️  压测结束，未检测到 queue.Full")


def verify_hand_online(side: str) -> tuple[bool, str]:
    """先 stop 轮询验证灵巧手在线；与复现阶段（默认轮询）分开。"""
    side_name = "左手" if side == "left" else "右手"
    print(f"预检灵巧手通信（{side_name} / {side}）...")
    try:
        with L6(side=side, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
            hand.stop_polling()
            hand.stop_stream()
            time.sleep(1.0)
            data = hand.angle.get_blocking(timeout_ms=VERIFY_TIMEOUT_MS)
            angles = [round(x, 2) for x in data.angles.to_list()]
            print(f"✅ 预检通过，角度: {angles}")
            return True, side
    except LinkerTimeoutError:
        print(f"❌ 预检失败：{side_name} 无应答（超时）")
        return False, side
    except Exception as e:
        print(f"❌ 预检失败：{type(e).__name__}: {e}")
        return False, side


def resolve_hand_side(preferred_side: str) -> str | None:
    ok, side = verify_hand_online(preferred_side)
    if ok:
        return side
    other = "left" if preferred_side == "right" else "right"
    if other == preferred_side:
        return None
    ok, side = verify_hand_online(other)
    if ok:
        if other != preferred_side:
            print(f'💡 请改用 HAND_SIDE = "{other}"')
        return side
    return None


def report_background_queue_full(
    *,
    monitor: PollingThreadMonitor,
    hand: L6,
    count: int,
    successful_reads: int,
    start_time: float,
) -> None:
    dead_threads = find_dead_polling_threads(hand)
    print(
        f"\n第{count}次主循环检测到后台 queue.Full"
        f"（主线程读角仍在继续，但轮询线程已异常）"
    )
    print_conclusion(
        count=count,
        successful_reads=successful_reads,
        elapsed=round(time.time() - start_time, 2),
        queue_full=True,
        source="后台轮询线程",
        background_hits=monitor.queue_full_hits,
        dead_threads=dead_threads,
    )


if __name__ == "__main__":
    print("=== 复现 queue.Full 问题 ===")
    print("阶段1：预检灵巧手是否在线（stop 轮询后读角）")
    print("阶段2：重新连接，保持默认轮询，循环读写直至 queue.Full")
    print("说明：已启用后台线程异常监听（threading.excepthook）\n")

    matched_side = resolve_hand_side(HAND_SIDE)
    if matched_side is None:
        print("\n结论：灵巧手未连接或 HAND_SIDE 错误，无法进入 queue.Full 复现。")
        print("请检查：是否上电、CAN 线、HAND_SIDE、PCAN 是否被占用。")
        sys.exit(1)

    print("\n阶段2：默认初始化，不关闭轮询，开始压测...")
    time.sleep(1)

    monitor = PollingThreadMonitor()
    monitor.install()

    count = 0
    successful_reads = 0
    start_time = time.time()
    queue_full_reported = False

    try:
        with L6(
            side=matched_side,
            interface_name=INTERFACE,
            interface_type=INTERFACE_TYPE,
        ) as hand:
            # 不调用 stop_polling()，用默认轮询（角度 60Hz + 力传感器 30Hz 等）
            hand.speed.set_speeds([20] * 6)
            time.sleep(0.5)

            while True:
                if monitor.detected_queue_full:
                    report_background_queue_full(
                        monitor=monitor,
                        hand=hand,
                        count=count,
                        successful_reads=successful_reads,
                        start_time=start_time,
                    )
                    queue_full_reported = True
                    break

                try:
                    count += 1
                    angle = hand.angle.get_blocking(timeout_ms=1000)
                    successful_reads += 1
                    if count % 10 == 0:
                        print(
                            f"第{count}次读角度: "
                            f"{[round(x, 2) for x in angle.angles.to_list()]}"
                        )

                    if count % 20 == 0:
                        print("发运动指令...")
                        hand.angle.set_angles([100, 100, 90, 90, 90, 90])
                        time.sleep(1)
                        hand.angle.set_angles([100, 100, 100, 100, 100, 100])
                        time.sleep(1)

                    time.sleep(0.1)

                except Exception as e:
                    print_conclusion(
                        count=count,
                        successful_reads=successful_reads,
                        elapsed=round(time.time() - start_time, 2),
                        queue_full=is_queue_full_error(e),
                        source="主线程",
                        error=e,
                        background_hits=monitor.queue_full_hits,
                        dead_threads=find_dead_polling_threads(hand),
                    )
                    queue_full_reported = is_queue_full_error(e) and successful_reads > 0
                    break

                if monitor.detected_queue_full:
                    report_background_queue_full(
                        monitor=monitor,
                        hand=hand,
                        count=count,
                        successful_reads=successful_reads,
                        start_time=start_time,
                    )
                    queue_full_reported = True
                    break
    finally:
        monitor.restore()

    sys.exit(0 if queue_full_reported else 1)
