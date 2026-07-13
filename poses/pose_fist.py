"""
pose_fist.py

【姿势说明】
  握拳：四指收拢，拇指内扣。

【运行】
  python pose_fist.py
"""

import sys
import time

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

from pose_common import resolve_hand_side, exit_if_hand_offline

HAND_SIDE = "right"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
MOTOR_SPEED = 20
ACTION_WAIT = 3
READ_TIMEOUT_MS = 1000

FIST_POSE = {
    "left": L6Angle(thumb_flex=20, thumb_abd=20, index=55, middle=50, ring=50, pinky=50),
    "right": L6Angle(thumb_flex=60, thumb_abd=20, index=30, middle=30, ring=30, pinky=30),
}

OPEN_POSE = L6Angle(
    thumb_flex=100, thumb_abd=100,
    index=100, middle=100, ring=100, pinky=100,
)

if __name__ == "__main__":
    if HAND_SIDE not in FIST_POSE:
        raise ValueError(f"HAND_SIDE 必须是 {list(FIST_POSE.keys())} 之一")

    matched_side = resolve_hand_side(HAND_SIDE, INTERFACE, INTERFACE_TYPE)
    if matched_side is None:
        sys.exit(1)

    print(f"=== 姿势：握拳（{matched_side}） ===")
    with L6(side=matched_side, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        exit_if_hand_offline(hand, HAND_SIDE)
        hand.speed.set_speeds([MOTOR_SPEED] * 6)

        try:
            hand.angle.set_angles(FIST_POSE[matched_side])
            time.sleep(ACTION_WAIT)
            current = [round(x, 2) for x in hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS).angles.to_list()]
            print(f"当前角度: {current}")
            print("✅ 握拳完成")
        finally:
            print("回到全张开安全位...")
            hand.angle.set_angles(OPEN_POSE)
            time.sleep(ACTION_WAIT)
