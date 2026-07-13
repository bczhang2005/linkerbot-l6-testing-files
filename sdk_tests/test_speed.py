"""
example_per_joint_speed.py

【示例说明】
  演示如何为六个关节分别设置不同运动速度。

  hand.speed.set_speeds([...]) 接收长度为 6 的列表，与关节一一对应：
  [thumb_flex, thumb_abd, index, middle, ring, pinky]
  数值越小越慢，越大越快（建议测试范围约 5~50）。

【演示内容】
  1. 拇指慢、四指快 → 握拳（拇指后到位）
  2. 四指慢、拇指快 → 回到全张开（拇指先到位）
  3. 逐指不同速度 → 半张开（各指速度差异明显）

【运行】
  python example_per_joint_speed.py
"""

import sys
import time

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

from pose_common import resolve_hand_side, exit_if_hand_offline

HAND_SIDE = "left"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
ACTION_WAIT = 4
READ_TIMEOUT_MS = 1000

JOINT_NAMES = [
    "thumb_flex（拇指弯曲）",
    "thumb_abd（拇指侧摆）",
    "index（食指）",
    "middle（中指）",
    "ring（无名指）",
    "pinky（小指）",
]

OPEN_POSE = L6Angle(
    thumb_flex=100, thumb_abd=100,
    index=100, middle=100, ring=100, pinky=100,
)

FIST_POSE = {
    "left": L6Angle(thumb_flex=20, thumb_abd=20, index=55, middle=50, ring=50, pinky=50),
    "right": L6Angle(thumb_flex=60, thumb_abd=20, index=30, middle=30, ring=30, pinky=30),
}

SEMI_OPEN_POSE = L6Angle(
    thumb_flex=60, thumb_abd=60,
    index=60, middle=60, ring=60, pinky=60,
)

# 示例速度配置：按需修改各关节数值
SPEED_SLOW_THUMB_FAST_FINGERS = [8, 8, 45, 45, 45, 45]
SPEED_FAST_THUMB_SLOW_FINGERS = [45, 45, 8, 8, 8, 8]
SPEED_STAGGERED = [15, 20, 50, 35, 25, 10]


def print_speeds(label: str, speeds: list[int]) -> None:
    print(f"\n--- {label} ---")
    for name, value in zip(JOINT_NAMES, speeds):
        print(f"  {name}: {value}")


def apply_speeds(hand, speeds: list[int], label: str) -> None:
    print_speeds(label, speeds)
    hand.speed.set_speeds(speeds)


def move_and_wait(hand, pose, step_name: str, wait: float = ACTION_WAIT) -> list[float]:
    print(f"\n>>> {step_name}")
    hand.angle.set_angles(pose)
    time.sleep(wait)
    current = [round(x, 2) for x in hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS).angles.to_list()]
    print(f"当前角度: {current}")
    return current


if __name__ == "__main__":
    matched_side = resolve_hand_side(HAND_SIDE, INTERFACE, INTERFACE_TYPE)
    if matched_side is None:
        sys.exit(1)

    print(f"\n=== 分关节速度示例（{matched_side}） ===")
    print("观察不同速度配置下，各手指到达目标的先后顺序。")

    with L6(side=matched_side, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        exit_if_hand_offline(hand, HAND_SIDE)

        try:
            apply_speeds(hand, [20] * 6, "初始：六关节统一低速 20")
            move_and_wait(hand, OPEN_POSE, "步骤 0：回到全张开")

            apply_speeds(hand, SPEED_SLOW_THUMB_FAST_FINGERS, "配置 A：拇指慢、四指快")
            move_and_wait(hand, FIST_POSE[matched_side], "步骤 1：握拳（四指先收拢，拇指较慢）", wait=5)

            apply_speeds(hand, SPEED_FAST_THUMB_SLOW_FINGERS, "配置 B：拇指快、四指慢")
            move_and_wait(hand, OPEN_POSE, "步骤 2：回到全张开（拇指先展开，四指较慢）", wait=5)

            apply_speeds(hand, SPEED_STAGGERED, "配置 C：逐指不同速度")
            move_and_wait(hand, SEMI_OPEN_POSE, "步骤 3：半张开（各指速度差异明显）", wait=5)

            apply_speeds(hand, [15] * 6, "收尾：统一低速回安全位")
            move_and_wait(hand, OPEN_POSE, "步骤 4：回到全张开安全位")

            print("\n✅ 分关节速度示例完成")
            print("\n提示：每次 hand.angle.set_angles(...) 前都可重新调用 set_speeds([...])")
            print("      修改上方 SPEED_* 常量即可自定义各指速度。")

        except Exception as e:
            print(f"\n❌ 运行出错：{type(e).__name__}: {e}")
            sys.exit(1)
