"""
完整示例.py

【测试目的】
  linkerbot 官方风格最简示例：设速 → 张开 → 握拳 → 阻塞读角度与温度。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电
  · 关闭 PCAN-View 等占用 PCAN 通道的程序
  · HAND_SIDE 与实物一致

【操作步骤】
  1. 修改 HAND_SIDE（left / right）
  2. 执行：python 完整示例.py

【预期结果】
  · 手指完成张开、握拳动作
  · 打印角度列表与温度列表

【实际结果】
  （测试后在此填写）

【说明】
  默认适配 Windows PCAN（PCAN_USBBUS1）；连接后会 stop 默认轮询，避免队列堵塞。
"""

from linkerbot import L6
import time

# ========== 顶部配置区（Windows PCAN） ==========
HAND_SIDE = "left"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
# =================================================

with L6(
    side=HAND_SIDE,
    interface_name=INTERFACE,
    interface_type=INTERFACE_TYPE,
) as hand:
    
    # 关闭默认轮询
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(0.5)

    # 设置速度
    hand.speed.set_speeds([50, 50, 50, 50, 50, 50])

    # 张开
    hand.angle.set_angles([100, 50, 100, 100, 100, 100])
    time.sleep(1)

    # 握拳
    hand.angle.set_angles([0, 0, 0, 0, 0, 0])
    time.sleep(1)

    # 读取状态
    angles = hand.angle.get_blocking()
    temps = hand.temperature.get_blocking()

    print(f"角度：{angles.angles.to_list()}")
    print(f"温度：{temps.temperatures.to_list()} °C")
