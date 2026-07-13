"""pose_*.py 脚本共用的灵巧手在线预检。"""

import sys
import time

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
from linkerbot.exceptions import TimeoutError as LinkerTimeoutError

VERIFY_TIMEOUT_MS = 3000
POLLING_SETTLE_SEC = 0.5


def print_hand_offline_help(last_error: str, preferred_side: str) -> None:
    side_name = "左手" if preferred_side == "left" else "右手"
    print("\n❌ 灵巧手未响应，无法执行姿势")
    print(f"   配置的 HAND_SIDE = \"{preferred_side}\"（{side_name}）")
    print(f"   原因：{last_error}")
    print("\n请检查：")
    print("  1. 灵巧手电源是否已打开（未插电/未上电时无法通信）")
    print("  2. CAN 线是否接好：PCAN 适配器 ↔ 灵巧手")
    print("  3. PCAN 驱动是否正常，是否被 PCAN-View 等程序占用")
    print("  4. HAND_SIDE 是否与实物一致（left / right）")
    print("\n建议先运行连接测试：")
    print("  cd setup && python test1_connect.py")
    print("  cd setup && python 硬件连接测试.py")


def verify_hand_online(hand, timeout_ms: int = VERIFY_TIMEOUT_MS) -> list[float]:
    """stop 默认轮询后阻塞读角；失败则仅开角度轮询再试一次。"""
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(POLLING_SETTLE_SEC)

    try:
        data = hand.angle.get_blocking(timeout_ms=timeout_ms)
        return [round(x, 2) for x in data.angles.to_list()]
    except LinkerTimeoutError:
        hand.stop_polling()
        hand.start_polling({SensorSource.ANGLE: 0.1})
        time.sleep(1.0)
        try:
            data = hand.angle.get_blocking(timeout_ms=timeout_ms)
            return [round(x, 2) for x in data.angles.to_list()]
        finally:
            hand.stop_polling()


def resolve_hand_side(
    preferred_side: str,
    interface: str,
    interface_type: str,
) -> str | None:
    """预检灵巧手是否上电在线；必要时自动尝试另一只 side。"""
    other = "right" if preferred_side == "left" else "left"
    last_error = "灵巧手无应答"

    for side in (preferred_side, other):
        side_name = "左手" if side == "left" else "右手"
        print(f"[预检] 检查灵巧手是否上电在线（{side_name} / {side}）...")
        try:
            with L6(
                side=side,
                interface_name=interface,
                interface_type=interface_type,
            ) as hand:
                angles = verify_hand_online(hand)
                print(f"✅ 灵巧手在线，当前角度: {angles}")
                if side != preferred_side:
                    print(f"💡 检测到应为另一只手，请改用 HAND_SIDE = \"{side}\"")
                return side
        except LinkerTimeoutError:
            last_error = f"{side_name} 读角超时（{VERIFY_TIMEOUT_MS} ms），可能未上电或未连接"
            print(f"❌ {last_error}")
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            print(f"❌ 预检失败: {last_error}")

    print_hand_offline_help(last_error, preferred_side)
    return None


def require_hand_online(hand, preferred_side: str) -> list[float] | None:
    """在已建立的连接上预检；失败则打印提示并返回 None。"""
    print("[预检] 检查灵巧手是否上电在线...")
    try:
        angles = verify_hand_online(hand)
        print(f"✅ 灵巧手在线，当前角度: {angles}")
        return angles
    except LinkerTimeoutError:
        print_hand_offline_help(
            f"读角超时（{VERIFY_TIMEOUT_MS} ms），可能未上电或未连接",
            preferred_side,
        )
        return None


def exit_if_hand_offline(hand, preferred_side: str) -> list[float]:
    """预检失败时以退出码 1 结束脚本。"""
    angles = require_hand_online(hand, preferred_side)
    if angles is None:
        sys.exit(1)
    return angles
