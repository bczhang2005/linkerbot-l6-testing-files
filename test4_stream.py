"""
test4_stream.py

【测试目的】
  验证流式读取：开启角度轮询后，通过 hand.stream() 持续接收 AngleEvent。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确
  · 须 stop 默认轮询后再自定义轮询（脚本内已处理）

【操作步骤】
  1. 修改 HAND_SIDE、RUN_SECONDS 等顶部配置
  2. 执行：python test4_stream.py

【预期结果】
  · 预检读角成功
  · RUN_SECONDS 内收到足够角度事件（≥ 理论值 75%）
  · 全部通过 → 退出码 0；否则 → 退出码 1

【实际结果】
  （测试后在此填写）

【说明】
  本脚本只读不动；可与 test3_read（blocking/snapshot）对比。
  温度轮询默认关闭，将 ENABLE_TEMPERATURE 设为 True 可开启。
"""

import sys
import time

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource, AngleEvent, TemperatureEvent
from linkerbot.exceptions import TimeoutError, ValidationError, StateError

# ========== 配置区 ==========
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"
RUN_SECONDS = 20
READ_TIMEOUT_MS = 3000
ANGLE_POLL_INTERVAL = 0.1       # 10Hz
STREAM_PRINT_EVERY = 10         # 每 N 次角度事件打印一行（10Hz 下 10≈每秒 1 条）
POLLING_SETTLE_SEC = 1.0
ENABLE_TEMPERATURE = False      # True 时额外开启温度轮询 2Hz
TEMP_POLL_INTERVAL = 0.5
MIN_EVENT_RATIO = 0.75          # 实际事件数 ≥ 理论值 × 此比例即通过
# ============================


def expected_angle_events():
    return int(RUN_SECONDS / ANGLE_POLL_INTERVAL)


def min_angle_events():
    return int(expected_angle_events() * MIN_EVENT_RATIO)


if __name__ == "__main__":
    hand_name = "左手" if HAND_SIDE == "left" else "右手"
    print(f"=== 流式读取测试（{hand_name}） ===")
    print(f"HAND_SIDE = \"{HAND_SIDE}\"，时长 = {RUN_SECONDS}s\n")

    angle_count = 0
    temp_count = 0
    stream_error = None

    try:
        with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
            hand.stop_polling()
            hand.stop_stream()
            time.sleep(POLLING_SETTLE_SEC)

            print("预检：阻塞读角度...")
            angle_data = hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS)
            preflight = [round(x, 2) for x in angle_data.angles.to_list()]
            print(f"✅ 灵巧手在线，角度: {preflight}\n")

            poll_config = {SensorSource.ANGLE: ANGLE_POLL_INTERVAL}
            if ENABLE_TEMPERATURE:
                poll_config[SensorSource.TEMPERATURE] = TEMP_POLL_INTERVAL
            hand.start_polling(poll_config)

            rate_hz = 1 / ANGLE_POLL_INTERVAL
            print(f"开始流式读取 {RUN_SECONDS}s（角度 {rate_hz:.0f}Hz，"
                  f"期望 ≥ {min_angle_events()} 次事件）...")

            start_time = time.time()
            try:
                for event in hand.stream():
                    match event:
                        case AngleEvent(data=data):
                            angle_count += 1
                            if angle_count % STREAM_PRINT_EVERY == 0:
                                angle_list = [round(x, 2) for x in data.angles.to_list()]
                                print(f"角度: {angle_list}")

                        case TemperatureEvent(data=data):
                            temp_count += 1
                            temp_list = [round(x, 2) for x in data.temperatures.to_list()]
                            print(f"温度: {temp_list} ℃")

                    if time.time() - start_time >= RUN_SECONDS:
                        break
            except Exception as e:
                stream_error = e
                print(f"❌ 流式读取中断: {type(e).__name__}: {e}")
            finally:
                hand.stop_polling()
                hand.stop_stream()
                print("已停止轮询和流式读取")

    except TimeoutError:
        print("❌ 预检读角或连接超时")
        sys.exit(1)
    except (ValidationError, StateError) as e:
        print(f"❌ {type(e).__name__}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        sys.exit(1)

    expected = expected_angle_events()
    minimum = min_angle_events()
    print(f"\n角度事件: {angle_count} 次（理论 {expected}，通过线 {minimum}）")
    if ENABLE_TEMPERATURE:
        print(f"温度事件: {temp_count} 次")

    print("\n" + "=" * 44)
    if stream_error:
        print("❌ 流式读取异常终止")
        sys.exit(1)

    if angle_count >= minimum:
        print("✅ 流式读取测试通过")
        sys.exit(0)

    print("❌ 角度事件不足，流式读取可能未正常工作")
    sys.exit(1)
