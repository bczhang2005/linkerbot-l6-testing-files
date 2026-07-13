"""
test_move_new.py

【测试目的】
  预设姿势运动测试（改进版）：集中 POSE_CONFIG，L6Angle/list 传参，每步阻塞读角，finally 回安全位。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 与 POSE_CONFIG 一致
  · 须 stop 默认轮询（脚本内已处理）；周围无障碍物

【操作步骤】
  1. 修改 HAND_SIDE、MOTOR_SPEED、ACTION_WAIT
  2. 执行：python test_move_new.py
  3. 观察各阶段动作与打印角度

【预期结果】
  · 序列：全张开 → 半张开 → 全张开 → 轻握拳(list) → 全张开
  · 每步打印当前角度；异常或结束时回到全张开

【实际结果】
  （测试后在此填写）

【说明】
  · ACTION_WAIT 控制每步等待；MOTOR_SPEED 控制运动快慢
  · 左右手姿势参数在 POSE_CONFIG 中分别配置
"""

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle
import time

# ========== 顶部配置区 ==========
HAND_SIDE = "left"  # 切左右手
INTERFACE = "PCAN_USBBUS1" 
INTERFACE_TYPE = "pcan"
MOTOR_SPEED = 20
ACTION_WAIT = 3  
# ========================================================

# 关节顺序与取值范围（0~100）：
# [thumb_flex, thumb_abd, index, middle, ring, pinky]
# L6Angle 字段顺序与列表顺序完全一致。

# ========== 📋 左右手姿势参数配置（集中管理） ==========
# 每只手的姿势：open(全张开) / semi_open(半张开) / fist(轻握拳)
# 同时提供 L6Angle（推荐，带字段名）和 list 两种形式：
# - 日常使用建议用 L6Angle（可读性好、有类型提示）
# - "fist_list" 专门保留用于演示/测试列表传参 API
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
    }
}

if HAND_SIDE not in POSE_CONFIG:
    raise ValueError(f"HAND_SIDE 必须是 {list(POSE_CONFIG.keys())} 之一，当前为 {HAND_SIDE!r}")

poses = POSE_CONFIG[HAND_SIDE]
hand_name = "左手" if HAND_SIDE == "left" else "右手"
# ====================================================================

# ========== 🛠️ 工具函数 ==========
def get_angle(hand, timeout_ms=1000):
    """读取当前角度，返回保留两位小数的列表 [thumb_flex, thumb_abd, index, middle, ring, pinky]"""
    angle_data = hand.angle.get_blocking(timeout_ms=timeout_ms)
    return [round(x, 2) for x in angle_data.angles.to_list()]

def run_action(hand, pose, action_name="", wait=None):
    """执行完整动作：发指令 → 等待 → 读角度 → 打印。

    pose 支持 L6Angle 或 list[int]，便于两种传参方式统一测试。
    """
    if action_name:
        print(f"\n--- {action_name} ---")
    hand.angle.set_angles(pose)
    time.sleep(wait if wait is not None else ACTION_WAIT)
    angle = get_angle(hand)
    print(f"当前角度: {angle}")
    return angle

def go_to_safe(hand):
    """回到全张开安全位，同时供 finally 保障使用。"""
    print("\n🔒 自动回到全张开安全位...")
    hand.angle.set_angles(poses["open"])
    time.sleep(ACTION_WAIT)
    print(f"安全位角度: {get_angle(hand)}")
# ==============================

if __name__ == "__main__":
    print(f"=== 开始运动测试（{hand_name}） ===")

    with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        # 关闭后台轮询，避免队列堵塞
        print("关闭后台轮询...")
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)

        # 设置速度
        hand.speed.set_speeds([MOTOR_SPEED] * 6)
        print(f"已设置低速模式：{MOTOR_SPEED}")

        try:
            # 1. 初始回到全张开
            run_action(hand, poses["open"], "初始状态：全张开")

            # 2. 测试数据类传参：半张开
            run_action(hand, poses["semi_open"], "测试数据类控制：半张开")

            # 3. 回到全张开
            run_action(hand, poses["open"], "回到全张开")

            # 4. 测试列表传参：轻握拳（演示 list 传参）
            run_action(hand, poses["fist_list"], "测试列表控制：轻握拳")

            # 5. 最终回到全张开
            run_action(hand, poses["open"], "回到全张开")

            print("\n✅ 测试完成")

        except Exception as e:
            print(f"\n❌ 测试出错：{type(e).__name__}: {e}")
        finally:
            go_to_safe(hand)
