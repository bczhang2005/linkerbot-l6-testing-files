"""
硬件连接测试.py（v3）

【测试目的】
  分层验证 PCAN/CAN 通道与灵巧手通信是否正常；自动尝试 left/right 诊断 HAND_SIDE 是否填错。

【前置条件】
  · 已激活 linkerbot 虚拟环境，已安装 linkerbot
  · PCAN 已插入，驱动正常，通道名为 PCAN_USBBUS1（可在 PCAN-View 中确认）
  · 测试阶段2 时：灵巧手已上电，CAN 线 PCAN↔灵巧手 已接好
  · 关闭 PCAN-View 等占用 PCAN 的程序

【操作步骤】
  1. 按实物修改下方 HAND_SIDE（left / right）
  2. 在 testing 目录执行：python 硬件连接测试.py
  3. 观察终端：阶段1（CAN 通道）→ 阶段2（读角度，方式1 失败则试方式2）
  4. 若当前 side 失败，脚本会自动用另一只手再测一次

【预期结果】
  · 仅插 PCAN、手未上电     → PCAN ✅，灵巧手 ❌
  · PCAN + 手上电 + side 正确 → PCAN ✅，灵巧手 ✅，并打印 6 路角度
  · side 填错               → 第一次失败，自动试另一只成功后提示正确 HAND_SIDE
  · PCAN 驱动/接口异常      → PCAN ❌

【实际结果】
  （测试后在此填写终端输出或结论）

【说明】
  L6 默认轮询含力传感器；无力传感器机型须先 stop_polling/stop_stream，否则读角易超时。
  本脚本方式1 同 test1_connect，方式2 同 test3_read（仅开角度轮询）。
"""

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
from linkerbot.exceptions import TimeoutError as LinkerTimeoutError
import time

# ========== 配置区 ==========
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"          # 先填你认为是哪只手；失败时会自动试另一只
READ_TIMEOUT_MS = 3000
RETRY_COUNT = 3
POLLING_SETTLE_SEC = 1.0     # stop_polling 后等待（与 test1_connect 一致）
# ============================


def try_read_angle(hand):
    last_err = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            print(f"      第 {attempt}/{RETRY_COUNT} 次 get_blocking（{READ_TIMEOUT_MS} ms）...")
            data = hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS)
            return True, [round(x, 2) for x in data.angles.to_list()]
        except LinkerTimeoutError as e:
            last_err = e
            time.sleep(0.5)
        except Exception as e:
            last_err = e
            print(f"      ⚠️  {type(e).__name__}: {e}")
            time.sleep(0.5)
    return False, last_err


def reset_polling(hand):
    """关闭默认轮询（含力传感器），避免无传感器机型队列堵塞。"""
    print("   → 关闭默认轮询 + 流式读取（stop_polling / stop_stream）")
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(POLLING_SETTLE_SEC)


def read_with_clean_queue(hand):
    """方式1：全停轮询后直接阻塞读（test1_connect 同款）。"""
    print("\n   [方式1] 全停轮询 → 直接读角度")
    reset_polling(hand)
    return try_read_angle(hand)


def read_with_angle_polling_only(hand):
    """方式2：只开角度轮询再读（test3_read 同款，无力传感器时更稳）。"""
    print("\n   [方式2] 全停轮询 → 仅开角度轮询(10Hz) → 读角度")
    reset_polling(hand)
    hand.start_polling({SensorSource.ANGLE: 0.1})
    time.sleep(1.0)
    return try_read_angle(hand)


def test_one_side(side):
    hand = None
    side_name = "左手" if side == "left" else "右手"
    print(f"\n--- 测试 HAND_SIDE = \"{side}\"（{side_name}）---")

    try:
        hand = L6(side=side, interface_name=INTERFACE, interface_type=INTERFACE_TYPE)
        print("✅ [阶段1] CAN 通道打开成功")
    except Exception as e:
        print(f"❌ [阶段1] CAN 通道失败: {type(e).__name__}: {e}")
        return False, False, e

    try:
        print("✅ [阶段2] 灵巧手通信测试开始")
        print("   说明：L6 默认轮询包含力传感器；你的机型若无力传感器，")
        print("         不先 stop_polling 会导致读角度一直超时。")

        ok, result = read_with_clean_queue(hand)
        if ok:
            print(f"   ✅ 方式1 成功: {result}")
            return True, True, result

        print("   ❌ 方式1 失败，尝试方式2...")
        ok, result = read_with_angle_polling_only(hand)
        if ok:
            print(f"   ✅ 方式2 成功: {result}")
            return True, True, result

        print("   ❌ 两种方式均失败")
        return True, False, result
    finally:
        try:
            hand.stop_polling()
            hand.stop_stream()
            hand.close()
        except Exception:
            pass


if __name__ == "__main__":
    print("=== 硬件连接分层测试（v3）===")
    print("  · 阶段1 = PCAN / CAN 通道")
    print("  · 阶段2 = 灵巧手通信（会先 stop 默认力传感器轮询）")
    print(f"  · 当前 HAND_SIDE = \"{HAND_SIDE}\"")
    print()

    can_ok, hand_ok, result = test_one_side(HAND_SIDE)
    matched_side = HAND_SIDE if hand_ok else None

    if can_ok and not hand_ok:
        other = "left" if HAND_SIDE == "right" else "right"
        print(f"\n[自动诊断] 尝试另一只手 HAND_SIDE = \"{other}\" ...")
        _, other_ok, other_result = test_one_side(other)
        if other_ok:
            matched_side = other
            hand_ok = True
            print(f"\n💡 请改用 HAND_SIDE = \"{other}\"")

    print("\n" + "=" * 44)
    if can_ok and hand_ok:
        print("结论：PCAN ✅  +  灵巧手 ✅")
        print(f"建议所有脚本统一：HAND_SIDE = \"{matched_side}\"")
        print("且连接后先：hand.stop_polling(); hand.stop_stream(); time.sleep(1)")
    elif can_ok and not hand_ok:
        print("结论：PCAN ✅  +  灵巧手 ❌")
        print("已 stop 力传感器轮询仍失败，请检查：")
        print("  1. 灵巧手是否上电、CAN 线是否接好")
        print("  2. PCAN-View 等是否占用通道")
        print("  3. HAND_SIDE 左右手是否都试过")
    else:
        print("结论：PCAN ❌  —  先解决 PCAN 驱动/接口名")
