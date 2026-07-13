"""
testing_fault.py

【测试目的】
  验证 fault 模块：阻塞读 get_blocking 与开启故障轮询后 get_snapshot 是否正常。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确
  · 脚本会先 stop 默认轮询

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python testing_fault.py
  3. 观察阻塞读与轮询快照两次结果

【预期结果】
  · get_blocking 返回故障数据（或超时/无故障时的合理响应）
  · 开 FAULT 1Hz 轮询 2 秒后 get_snapshot 有数据

【实际结果】
  （测试后在此填写）

【说明】
  用于排查故障模块 API 是否可用；与 test1_connect 中 fault 读法互补。
"""

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
import time

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"

if __name__ == "__main__":
    print("=== fault模块验证 ===")
    with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)
        print("✅ 连接成功")

        print("\n1. 阻塞读get_blocking:")
        try:
            data = hand.fault.get_blocking(timeout_ms=2000)
            print(f"   ✅ 成功: {data}")
        except Exception as e:
            print(f"   ❌ 失败: {type(e).__name__}: {e}")

        print("\n2. 开故障轮询后读快照:")
        hand.start_polling({SensorSource.FAULT: 1.0})
        time.sleep(2)
        try:
            data = hand.fault.get_snapshot()
            if data:
                print(f"   ✅ 成功: {data}")
            else:
                print(f"   ❌ 无数据")
        except Exception as e:
            print(f"   ❌ 失败: {type(e).__name__}: {e}")

        hand.stop_polling()
        print("\n=== 测试完成 ===")