"""
pose_peace.py

【姿势说明】
  剪刀手（比耶）：食指与中指伸直，其余手指收拢。

【运行】
  python pose_peace.py
"""

import sys
import time

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

from pose_common import resolve_hand_side, exit_if_hand_offline

HAND_SIDE = "right"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
MOTOR_SPEED = 50
ACTION_WAIT = 3
READ_TIMEOUT_MS = 1000

PEACE_POSE = {
    "left": L6Angle(thumb_flex=25, thumb_abd=30, index=100, middle=100, ring=22, pinky=18),
    "right": L6Angle(thumb_flex=50, thumb_abd=25, index=100, middle=100, ring=22, pinky=18),
}

OPEN_POSE = L6Angle(
    thumb_flex=100, thumb_abd=100,
    index=100, middle=100, ring=100, pinky=100,
)

if __name__ == "__main__":
    if HAND_SIDE not in PEACE_POSE:
        raise ValueError(f"HAND_SIDE 必须是 {list(PEACE_POSE.keys())} 之一")

    matched_side = resolve_hand_side(HAND_SIDE, INTERFACE, INTERFACE_TYPE)
    if matched_side is None:
        sys.exit(1)

    print(f"=== 姿势：剪刀手（{matched_side}） ===")
    with L6(side=matched_side, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        exit_if_hand_offline(hand, HAND_SIDE)
        hand.speed.set_speeds([MOTOR_SPEED] * 6)

        try:
            hand.angle.set_angles(PEACE_POSE[matched_side])
            time.sleep(ACTION_WAIT)
            current = [round(x, 2) for x in hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS).angles.to_list()]
            print(f"当前角度: {current}")
            print("✅ 剪刀手完成")
        finally:
            print("回到全张开安全位...")
            hand.angle.set_angles(OPEN_POSE)
            time.sleep(ACTION_WAIT)
