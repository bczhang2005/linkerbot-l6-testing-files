"""
test3_read.py

【测试目的】
  对比三种角度读取方式：阻塞读 get_blocking、模块缓存 get_snapshot、
  全局快照 hand.get_snapshot().angle。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确
  · 脚本会先 stop 默认轮询，再只开角度轮询（10Hz）

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python test3_read.py

【预期结果】
  · 三种读角方式均有数据，且与阻塞读最大误差 < MAX_ANGLE_DIFF（默认 1）
  · 温度/力传感器快照无数据属正常（未开对应轮询）
  · 全部通过 → 退出码 0；任一项失败 → 退出码 1

【实际结果】
  （测试后在此填写）

【说明】
  只开 SensorSource.ANGLE 轮询，避免力传感器轮询堵队列。
  开头会先演示「全停轮询时的 blocking 读」，不计入三项 pass/fail。
"""

import sys
import time

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
from linkerbot.exceptions import TimeoutError, ValidationError, StateError

# ========== 配置区 ==========
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"
READ_TIMEOUT_MS = 3000
MAX_ANGLE_DIFF = 1.0
POLLING_INTERVAL_SEC = 0.1  # 10Hz
POLLING_WARMUP_SEC = 1.0
POLLING_SETTLE_SEC = 1.0
# ============================


def to_angle_list(angle_data):
    return [round(x, 2) for x in angle_data.angles.to_list()]


def max_diff(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


if __name__ == "__main__":
    hand_name = "左手" if HAND_SIDE == "left" else "右手"
    print(f"=== 三种读取方式对比（{hand_name}） ===")
    print(f"HAND_SIDE = \"{HAND_SIDE}\"，误差阈值 = {MAX_ANGLE_DIFF}\n")

    exit_code = 1
    checks = {
        "blocking": False,
        "module_snapshot": False,
        "global_snapshot": False,
    }

    try:
        with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
            hand.stop_polling()
            hand.stop_stream()
            time.sleep(POLLING_SETTLE_SEC)

            # 参考：全停轮询时的 blocking（不计入三项结论）
            print("=== 参考：全停轮询时的 blocking 读 ===")
            try:
                baseline = to_angle_list(hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS))
                print(f"角度: {baseline}")
            except TimeoutError:
                print("❌ 阻塞读超时（后续对比可能无意义）")

            print("\n开启角度轮询（10Hz），等待缓存更新...")
            hand.start_polling({SensorSource.ANGLE: POLLING_INTERVAL_SEC})
            time.sleep(POLLING_WARMUP_SEC)

            try:
                print("\n=== 1. 阻塞读 get_blocking ===")
                block_list = to_angle_list(hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS))
                print(f"角度: {block_list}")
                checks["blocking"] = True

                print("\n=== 2. 模块缓存 angle.get_snapshot ===")
                angle_cache = hand.angle.get_snapshot()
                if not angle_cache:
                    print("❌ 无缓存数据")
                else:
                    cache_list = to_angle_list(angle_cache)
                    diff = max_diff(block_list, cache_list)
                    print(f"角度: {cache_list}")
                    print(f"与阻塞读最大误差: {round(diff, 2)}")
                    checks["module_snapshot"] = diff < MAX_ANGLE_DIFF

                print("\n=== 3. 全局快照 hand.get_snapshot().angle ===")
                full_snap = hand.get_snapshot()
                if not full_snap.angle:
                    print("❌ 快照中无角度数据")
                else:
                    snap_list = to_angle_list(full_snap.angle)
                    diff = max_diff(block_list, snap_list)
                    print(f"角度: {snap_list}")
                    print(f"与阻塞读最大误差: {round(diff, 2)}")
                    checks["global_snapshot"] = diff < MAX_ANGLE_DIFF

                print("\n=== 其它传感器缓存（仅展示，不影响结论） ===")
                if full_snap.temperature:
                    print(f"温度: {full_snap.temperature.temperatures.to_list()}")
                else:
                    print("温度: 无数据（未开温度轮询，正常）")

                if full_snap.force_sensor:
                    print(f"力传感器: 有数据，拇指 = {full_snap.force_sensor.thumb.values}")
                else:
                    print("力传感器: 无数据（未开轮询或硬件无传感器，正常）")

            finally:
                hand.stop_polling()
                print("\n已关闭角度轮询")

    except TimeoutError:
        print("❌ 连接或读角超时")
        sys.exit(1)
    except (ValidationError, StateError) as e:
        print(f"❌ {type(e).__name__}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        sys.exit(1)

    print("\n" + "=" * 44)
    print(f"阻塞读:     {'✅' if checks['blocking'] else '❌'}")
    print(f"模块缓存:   {'✅' if checks['module_snapshot'] else '❌'}")
    print(f"全局快照:   {'✅' if checks['global_snapshot'] else '❌'}")

    if all(checks.values()):
        print("\n✅ 三种读取方式测试通过")
        sys.exit(0)

    print("\n❌ 测试未全部通过")
    if checks["blocking"] and not all(checks.values()):
        print("提示：阻塞读成功但缓存不一致时，可加长 POLLING_WARMUP_SEC 后重试")
    sys.exit(1)
