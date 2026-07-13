"""
test2_move_fail.py

【测试目的】
  对照实验：与 test2_move.py 相同动作序列，但**不** stop 默认轮询，演示队列堵塞导致读角/运动异常。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电
  · 无力传感器机型上本脚本更容易失败（与 test2_move.py 对比）

【操作步骤】
  1. 先运行 test2_move.py（正常），再运行本脚本（异常对照）
  2. 执行：python test2_move_fail.py
  3. 观察是否在 get_blocking 或运动阶段超时/出错

【预期结果】
  · 可能读角超时、动作卡顿或 queue 相关错误
  · 用于理解为何必须 hand.stop_polling() / stop_stream()

【实际结果】
  （测试后在此填写）

【说明】
  stop_polling 相关代码被故意注释；姿势与 test2_move.py 相同。
  验证通过后请使用 test2_move.py。
"""

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle
import time

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"

# 与 test2_move.py / test_move_new.py 保持一致
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
        
        # 未关闭后台轮询
        print("未关闭后台轮询")
        # hand.stop_polling()
        # hand.stop_stream()
        # time.sleep(0.5)
        
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