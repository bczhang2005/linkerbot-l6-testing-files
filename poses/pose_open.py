"""
pose_open.py

【姿势说明】
  全张开：六个关节均为 100，安全复位位。

【运行】
  python pose_open.py
"""

import sys
import time

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

from pose_common import resolve_hand_side, exit_if_hand_offline

HAND_SIDE = "left"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
MOTOR_SPEED = 20
ACTION_WAIT = 3
READ_TIMEOUT_MS = 1000

OPEN_POSE = L6Angle(
    thumb_flex=100, thumb_abd=100,
    index=100, middle=100, ring=100, pinky=100,
)

if __name__ == "__main__":
    matched_side = resolve_hand_side(HAND_SIDE, INTERFACE, INTERFACE_TYPE)
    if matched_side is None:
        sys.exit(1)

    print(f"=== 姿势：全张开（{matched_side}） ===")
    with L6(side=matched_side, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        exit_if_hand_offline(hand, HAND_SIDE)
        hand.speed.set_speeds([MOTOR_SPEED] * 6)

        hand.angle.set_angles(OPEN_POSE)
        time.sleep(ACTION_WAIT)

        current = [round(x, 2) for x in hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS).angles.to_list()]
        print(f"当前角度: {current}")
        print("✅ 全张开完成")
