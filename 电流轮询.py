"""
电流轮询.py

【测试目的】
  验证 current 模块：不开轮询阻塞读、开 1Hz 轮询读快照、开轮询后再阻塞读。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python 电流轮询.py
  3. 依次观察三步输出

【预期结果】
  · 三步中至少一种方式能读到电流数据（视硬件是否支持）

【实际结果】
  （测试后在此填写）

【说明】
  用于确认电流模块 API；不支持时可能三步均失败，属硬件能力问题。
"""

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
import time

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"

if __name__ == "__main__":
    print("=== 电流模块验证测试 ===")
    with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)
        print("✅ 连接成功")

        # 先试阻塞读（不开轮询）
        print("\n1. 不开轮询，直接阻塞读:")
        try:
            data = hand.current.get_blocking(timeout_ms=2000)
            print(f"   ✅ 成功: {data}")
        except Exception as e:
            print(f"   ❌ 失败: {type(e).__name__}: {e}")

        # 开启电流的轮询，等2秒更新缓存
        print("\n2. 开启电流轮询（1Hz），等2秒后读快照:")
        hand.start_polling({SensorSource.CURRENT: 1.0})
        time.sleep(2)
        
        try:
            data = hand.current.get_snapshot()
            if data:
                print(f"   ✅ 成功: {data}")
            else:
                print(f"   ❌ 还是无数据")
        except Exception as e:
            print(f"   ❌ 失败: {type(e).__name__}: {e}")

        # 开轮询的情况下再试阻塞读
        print("\n3. 开轮询的情况下阻塞读:")
        try:
            data = hand.current.get_blocking(timeout_ms=2000)
            print(f"   ✅ 成功: {data}")
        except Exception as e:
            print(f"   ❌ 失败: {type(e).__name__}: {e}")

        hand.stop_polling()
        print("\n=== 测试完成 ===")