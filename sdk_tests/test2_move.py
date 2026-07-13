"""
test2_move.py

【测试目的】
  验证手指运动控制：L6Angle 数据类传参与 list 列表传参两种方式，每步后用 get_blocking 读角验证。

【前置条件】
  · 已激活 linkerbot 虚拟环境；PCAN 已连接，灵巧手已上电
  · HAND_SIDE 与实物一致；周围无障碍物，建议低速测试
  · 脚本会 stop 默认轮询后再发运动指令

【操作步骤】
  1. 修改 HAND_SIDE、速度（默认各关节 speed=20）
  2. 执行：python test2_move.py
  3. 观察各阶段标题与「当前角度」输出，确认手指随指令运动

【预期结果】
  · 动作序列：全张开 → 半张开 → 全张开 → 轻握拳 → 全张开
  · 每步后 get_blocking 返回的角度与目标姿势大致一致
  · 最后显示「✅ 测试完成」

【实际结果】
  （测试后在此填写终端输出或结论）

【说明】
  · 每步 sleep 3 秒；关节顺序：[thumb_flex, thumb_abd, index, middle, ring, pinky]
  · 姿势数值与 test_move_new.py 的 POSE_CONFIG 一致（按 HAND_SIDE 选 left/right）
"""

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle
import time

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"

# 与 test_move_new.py 保持一致
POSE_CONFIG = {
    "left": {
        "open": L6Angle(thumb_flex=100, thumb_abd=100, index=100, middle=100, ring=100, pinky=100),
        "semi_open": L6Angle(thumb_flex=60, thumb_abd=60, index=60, middle=60, ring=60, pinky=60),
        "fist": L6Angle(thumb_flex=20, thumb_abd=20, index=55, middle=50, ring=50, pinky=50),
        "fist_list": [20, 20, 55, 50, 50, 50],
    },
    "right": {
        "open": L6Angle(thumb_flex=100, thumb_abd=100, index=100, middle=100, ring=100, pinky=100),
        "semi_open": L6Angle(thumb_flex=60, thumb_abd=60, index=60, middle=60, ring=60, pinky=60),
        "fist": L6Angle(thumb_flex=60, thumb_abd=20, index=30, middle=30, ring=30, pinky=30),
        "fist_list": [60, 20, 30, 30, 30, 30],
    },
}

if HAND_SIDE not in POSE_CONFIG:
    raise ValueError(f"HAND_SIDE 必须是 {list(POSE_CONFIG.keys())} 之一，当前为 {HAND_SIDE!r}")

poses = POSE_CONFIG[HAND_SIDE]
open_pose = poses["open"]
semi_open_pose = poses["semi_open"]
fist_list = poses["fist_list"]

if __name__ == "__main__":
    with L6(
        side=HAND_SIDE,
        interface_name=INTERFACE,
        interface_type=INTERFACE_TYPE
    ) as hand:
        
        # 暂时关闭后台轮询，避免队列堵塞
        print("暂时关闭后台轮询")
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)
        
        # 设置低速，保证安全
        hand.speed.set_speeds([20, 20, 20, 20, 20, 20])
        print("已设置低速模式")

        # 初始，回到全张开
        print("\n--- 初始状态：全张开 ---")
        hand.angle.set_angles(open_pose)
        time.sleep(3)
        
        # 读取当前角度，验证是否到位
        current_angle = hand.angle.get_blocking()
        print(f"当前角度: {[round(x, 2) for x in current_angle.angles.to_list()]}")
        time.sleep(3)
        
        # 方式1：数据类传参（推荐，有类型提示）
        print("\n--- 测试数据类控制：半张开 ---")
        hand.angle.set_angles(semi_open_pose)
        time.sleep(3)

        # 读取当前角度，验证是否到位
        current_angle = hand.angle.get_blocking()
        print(f"当前角度: {[round(x, 2) for x in current_angle.angles.to_list()]}")
        time.sleep(3)
        
        # 回到张开
        print("\n--- 回到张开 ---")
        hand.angle.set_angles(open_pose)  
        time.sleep(3)  
        
        # 读取当前角度，验证是否到位
        current_angle = hand.angle.get_blocking()
        print(f"当前角度: {[round(x, 2) for x in current_angle.angles.to_list()]}")
        time.sleep(3) 

        # 方式2：列表传参（简洁）
        print("\n--- 测试列表控制：轻握拳 ---")
        hand.angle.set_angles(fist_list)
        time.sleep(3)
        
        # 读取当前角度，验证是否到位
        current_angle = hand.angle.get_blocking()
        print(f"当前角度: {[round(x, 2) for x in current_angle.angles.to_list()]}")
        time.sleep(3)

        # 回到全张开
        print("\n--- 回到全张开 ---")
        hand.angle.set_angles(open_pose)  
        time.sleep(3) 

        # 读取最终角度
        final_angle = hand.angle.get_blocking()
        print(f"最终角度: {[round(x,2) for x in final_angle.angles.to_list()]}")
        time.sleep(3)

        print("\n✅ 测试完成")