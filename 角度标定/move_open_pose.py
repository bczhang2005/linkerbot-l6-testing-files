"""
move_open_pose.py

【测试目的】
  将机械手回到全张开安全位（六个关节均为 100）。

【前置条件】
  · 已激活 linkerbot 虚拟环境；PCAN 已连接，灵巧手已上电
  · HAND_SIDE 与实物一致；周围无障碍物

【操作步骤】
  1. 修改 HAND_SIDE、MOTOR_SPEED、ACTION_WAIT
  2. 执行：python move_open_pose.py

【预期结果】
  · 手指移动到全张开位，get_blocking 读角接近 [100, 100, 100, 100, 100, 100]

【实际结果】
  （测试后在此填写）

【说明】
  · 关节顺序：[thumb_flex, thumb_abd, index, middle, ring, pinky]，取值 0~100
  · 左右手 open pose 均为全 100
"""

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle
import time

# ========== 顶部配置区 ==========
HAND_SIDE = "left"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
MOTOR_SPEED = 20
ACTION_WAIT = 3
READ_TIMEOUT_MS = 1000
# ========================================================

OPEN_POSE = L6Angle(
    thumb_flex=100,
    thumb_abd=100,
    index=100,
    middle=100,
    ring=100,
    pinky=100,
)

if __name__ == "__main__":
    hand_name = "左手" if HAND_SIDE == "left" else "右手"
    print(f"=== 回到全张开安全位（{hand_name}） ===")

    with L6(
        side=HAND_SIDE,
        interface_name=INTERFACE,
        interface_type=INTERFACE_TYPE,
    ) as hand:
        print("关闭后台轮询...")
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)

        hand.speed.set_speeds([MOTOR_SPEED] * 6)
        print(f"已设置低速模式：{MOTOR_SPEED}")

        print("\n--- 移动到全张开 (100) ---")
        hand.angle.set_angles(OPEN_POSE)
        time.sleep(ACTION_WAIT)

        angle_data = hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS)
        current = [round(x, 2) for x in angle_data.angles.to_list()]
        print(f"当前角度: {current}")
        print("\n✅ 已回到全张开安全位")
