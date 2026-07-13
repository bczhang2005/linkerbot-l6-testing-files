"""
test_version.py

【测试目的】
  读取 L6 灵巧手设备版本信息（序列号、PCB/固件/机械版本）。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确
  · 建议先通过 test1_connect.py 确认连接正常

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python test_version.py

【预期结果】
  · 成功 → 打印 DeviceInfo 各字段，退出码 0
  · 超时或失败 → 退出码 1

【实际结果】
  （测试后在此填写）

【说明】
  连接后 stop 默认轮询，再调用 hand.version.get_device_info()。
"""

import sys
import time

from linkerbot import L6
from linkerbot.exceptions import TimeoutError

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"


if __name__ == "__main__":
    try:
        with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
            hand.stop_polling()
            hand.stop_stream()
            time.sleep(1)

            info = hand.version.get_device_info()
            print(f"序列号:   {info.serial_number}")
            print(f"PCB:      {info.pcb_version}")
            print(f"固件:     {info.firmware_version}")
            print(f"机械:     {info.mechanical_version}")
            print(f"时间戳:   {info.timestamp}")
            print("\n✅ 版本读取成功")
            sys.exit(0)
    except TimeoutError:
        print("❌ 版本读取超时")
        sys.exit(1)
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        sys.exit(1)
