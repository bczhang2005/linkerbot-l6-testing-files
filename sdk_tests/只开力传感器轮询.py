"""
只开力传感器轮询.py

【测试目的】
  隔离测试：仅开启力传感器 10Hz 轮询，30 秒内每秒 get_snapshot，观察是否超时/堵队列。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电
  · 硬件须具备力传感器；若无则持续「无数据」为正常

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python 只开力传感器轮询.py
  3. 观察 30 秒内每秒读力传感器快照

【预期结果】
  · 有力传感器：周期性读到数据，无异常退出
  · 无力传感器：多为「无数据」，不应导致 queue.Full（已 stop 默认轮询）

【实际结果】
  （测试后在此填写）

【说明】
  与「只开角度轮询.py」成对，用于排查轮询类型对队列的影响。
"""

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
import time

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"

if __name__ == "__main__":
    print("=== 测试2：只开力传感器轮询（10Hz） ===")
    with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        # 先停掉所有默认轮询，清空状态
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)

        # 只开力传感器轮询，10Hz
        print("✅ 只开启力传感器轮询，开始测试30秒...")
        hand.start_polling({SensorSource.FORCE_SENSOR: 0.1})

        # 每隔1秒读一次力传感器，看会不会超时、会不会堵
        start_time = time.time()
        count = 0
        while time.time() - start_time < 30:
            try:
                force_snap = hand.force_sensor.get_snapshot()
                count += 1
                if force_snap:
                    print(f"第{count}次：✅ 读到力传感器数据")
                else:
                    print(f"第{count}次：⚠️  力传感器无数据")
                time.sleep(1)
            except Exception as e:
                print(f"❌ 第{count}次出错了：{e}")
                break
        
        print("\n测试2结束")
        hand.stop_polling()