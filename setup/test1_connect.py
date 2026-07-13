"""
test1_connect.py

【测试目的】
  验证 PCAN 能否打开、灵巧手能否读角（基础连接测试）。

【前置条件】
  · 已激活 linkerbot 虚拟环境；PCAN 已连接，灵巧手已上电
  · 关闭 PCAN-View 等占用 PCAN 通道的程序
  · HAND_SIDE 与实物一致（填错时脚本会自动试另一只手）

【操作步骤】
  1. 修改 HAND_SIDE（left / right）
  2. 执行：python test1_connect.py

【预期结果】
  · PCAN ✅ + 读角 ✅ → 「✅ 硬件连接成功」，退出码 0
  · PCAN ✅ + 读角 ❌ → 提示检查上电/接线/HAND_SIDE，退出码 1
  · PCAN ❌ → 提示检查驱动/接口/通道占用，退出码 1

【实际结果】
  （测试后在此填写终端输出或结论）

【说明】
  连接后 stop_polling / stop_stream 并等待 1 秒，避免无力传感器机型默认轮询堵队列。
  读角失败时会再试「仅角度轮询」；仍失败则自动换另一只 side。
"""

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
from linkerbot.exceptions import TimeoutError, ValidationError, StateError
import sys
import time

# ========== 顶部配置区 ==========
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"
READ_TIMEOUT_MS = 3000
RETRY_COUNT = 3
# ==================================


def read_angle(hand):
    """stop 默认轮询后读角；失败则仅开角度轮询再试一次。"""
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(1)

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            data = hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS)
            return True, [round(x, 2) for x in data.angles.to_list()]
        except TimeoutError:
            if attempt < RETRY_COUNT:
                time.sleep(0.5)

    hand.stop_polling()
    hand.start_polling({SensorSource.ANGLE: 0.1})
    time.sleep(1)
    try:
        data = hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS)
        return True, [round(x, 2) for x in data.angles.to_list()]
    except TimeoutError:
        return False, None
    finally:
        hand.stop_polling()


def test_side(side):
    side_name = "左手" if side == "left" else "右手"
    print(f"\n--- HAND_SIDE = \"{side}\"（{side_name}）---")
    try:
        with L6(side=side, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
            print("CAN 通道已打开，正在读角度...")
            ok, angles = read_angle(hand)
            if ok:
                print(f"✅ 角度: {angles}")
            else:
                print("❌ 读角失败")
            return True, ok, angles
    except TimeoutError:
        print("❌ 连接超时")
        return False, False, None
    except (ValidationError, StateError) as e:
        print(f"❌ {type(e).__name__}: {e}")
        return False, False, None
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        return False, False, None


if __name__ == "__main__":
    print("=== test1：连接测试 ===")
    print(f"HAND_SIDE = \"{HAND_SIDE}\"\n")

    can_ok, hand_ok, _ = test_side(HAND_SIDE)
    matched_side = HAND_SIDE if hand_ok else None

    if can_ok and not hand_ok:
        other = "right" if HAND_SIDE == "left" else "left"
        print(f"\n尝试另一只 side: \"{other}\" ...")
        _, hand_ok, _ = test_side(other)
        if hand_ok:
            matched_side = other
            print(f"\n💡 请改用 HAND_SIDE = \"{other}\"")

    print("\n" + "=" * 40)
    if not can_ok:
        print("结论：PCAN ❌")
        sys.exit(1)
    if not hand_ok:
        print("结论：PCAN ✅  灵巧手 ❌")
        sys.exit(1)

    print("结论：PCAN ✅  灵巧手 ✅")
    if matched_side:
        print(f"建议 HAND_SIDE = \"{matched_side}\"")
    print("\n✅ 硬件连接成功")
    sys.exit(0)
