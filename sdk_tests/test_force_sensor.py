"""
test_force_sensor.py

【测试目的】
  验证硬件是否具备力传感器：先确认灵巧手在线，再仅开 FORCE_SENSOR 轮询并 get_blocking 读力数据。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python test_force_sensor.py
  3. 观察预检与力传感器读取结论

【预期结果】
  · 手未上电/连错手 → 预检失败，提示检查连接（不会误判为「无力传感器」）
  · 手在线 + 有力传感器 → ✅ 打印力数据
  · 手在线 + 无力传感器 → ℹ️ 读力超时，提示可能无阻传感器/未启用

【实际结果】
  （测试后在此填写）

【说明】
  无力传感器时应避免开启 FORCE_SENSOR 轮询；日常脚本须 stop 默认轮询。
"""

import sys
import time
from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
from linkerbot.exceptions import TimeoutError as LinkerTimeoutError

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"
VERIFY_TIMEOUT_MS = 3000
FORCE_READ_TIMEOUT_MS = 2000


def verify_hand_online(hand):
    """预检：灵巧手能否正常读角（与力传感器测试无关）。"""
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(1.0)
    data = hand.angle.get_blocking(timeout_ms=VERIFY_TIMEOUT_MS)
    return [round(x, 2) for x in data.angles.to_list()]


def resolve_hand_side(preferred_side):
    sides = [preferred_side]
    other = "left" if preferred_side == "right" else "right"
    sides.append(other)

    last_error = "灵巧手无应答"
    for side in sides:
        side_name = "左手" if side == "left" else "右手"
        print(f"[预检] 验证灵巧手通信（{side_name} / {side}）...")
        try:
            with L6(side=side, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
                angles = verify_hand_online(hand)
                print(f"✅ 预检通过，角度: {angles}")
                if side != preferred_side:
                    print(f"💡 请改用 HAND_SIDE = \"{side}\"")
                return side
        except LinkerTimeoutError:
            last_error = f"{side_name} 读角超时（{VERIFY_TIMEOUT_MS} ms）"
            print(f"❌ {last_error}")
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            print(f"❌ 预检失败: {last_error}")

    print(f"\n结论：灵巧手未连接或 HAND_SIDE 错误（{last_error}）")
    print("请先解决连接问题，再判断力传感器是否存在。")
    return None


def test_force_sensor_read(hand):
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(0.5)

    print("\n[力传感器] 开启 FORCE_SENSOR 轮询（10Hz）...")
    hand.start_polling({SensorSource.FORCE_SENSOR: 0.1})
    time.sleep(1.0)

    print("[力传感器] 尝试 get_blocking 读取...")
    try:
        force_data = hand.force_sensor.get_blocking(timeout_ms=FORCE_READ_TIMEOUT_MS)
        print("✅ 成功读到力传感器数据")
        print(f"   拇指数据形状: {force_data.thumb.values.shape}")
        print(f"   食指第一个值: {force_data.index.values[0][0]}")
        return "has_sensor"
    except LinkerTimeoutError as e:
        print(f"❌ 读力超时（{FORCE_READ_TIMEOUT_MS} ms）: {e}")
        print("\n👉 结论：灵巧手在线，但未读到力传感器数据")
        print("   可能原因：本机型无力传感器 / 力传感器未启用 / 固件未开放")
        print("   这也解释了默认力传感器轮询可能导致 queue.Full。")
        return "no_sensor"
    except Exception as e:
        print(f"❌ 读力失败: {type(e).__name__}: {e}")
        print("\n👉 结论：灵巧手在线，力传感器读取出现非超时错误")
        print("   请查 SDK 版本、固件或联系厂商；不要与「手未连接」混淆。")
        return "error"


if __name__ == "__main__":
    print("=== 力传感器检测 ===")
    print("阶段1：预检灵巧手是否在线（读角度）")
    print("阶段2：仅开力传感器轮询并读力\n")

    matched_side = resolve_hand_side(HAND_SIDE)
    if matched_side is None:
        sys.exit(1)

    print(f"\n阶段2：在已确认的 HAND_SIDE=\"{matched_side}\" 上测试力传感器...")
    with L6(
        side=matched_side,
        interface_name=INTERFACE,
        interface_type=INTERFACE_TYPE,
    ) as hand:
        result = test_force_sensor_read(hand)
        hand.stop_polling()

    print()
    if result == "has_sensor":
        print("总结：✅ 灵巧手在线，且检测到力传感器")
    elif result == "no_sensor":
        print("总结：✅ 灵巧手在线，ℹ️  未检测到力传感器（或不可用）")
    else:
        print("总结：✅ 灵巧手在线，❌ 力传感器读取出错（见上方详情）")
