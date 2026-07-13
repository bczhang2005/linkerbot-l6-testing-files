"""
test_move_stream.py

【测试目的】
  合并 test_move_new.py 与 test4_stream.py：后台线程执行预设动作序列的同时，
  主线程通过 hand.stream() 流式读取并打印角度（可选温度）变化。

【前置条件】
  · 已激活 linkerbot 虚拟环境，灵巧手已上电，PCAN 连接正常
  · HAND_SIDE 与实物一致；无力传感器机型须 stop 默认轮询（脚本内已处理）
  · 关闭 PCAN-View 等占用 PCAN 的程序

【操作步骤】
  1. 修改顶部配置：HAND_SIDE、MOTOR_SPEED、ACTION_WAIT 等
  2. 执行：python test_move_stream.py
  3. 观察终端：动作阶段标题 + [流式] 角度输出
  4. 动作结束后自动停轮询并回到全张开安全位

【预期结果】
  · 动作序列：全张开 → 半张开 → 全张开 → 轻握拳 → 全张开（共 5 步）
  · 流式读角：动作进行期间持续打印角度，与手指运动同步变化
  · 结束：打印角度/温度事件计数，显示「✅ 测试完成」

【实际结果】
  （测试后在此填写终端输出或结论）

【时间与参数说明】
  · 总时长 ≈ 5 × ACTION_WAIT（默认 5×3=15 秒）+ 实际运动时间 + 收尾安全位
  · MOTOR_SPEED：越小越慢（默认 20）
  · ACTION_WAIT：每个动作发指令后的等待秒数（默认 3）
  · ANGLE_POLL_INTERVAL：角度轮询间隔，0.1 = 10Hz
  · STREAM_PRINT_EVERY：每 N 次角度事件打印一次（10Hz 下 10≈每秒 1 条）
  · 无固定 RUN_SECONDS；流式读取在动作线程结束后自动停止
"""

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle, SensorSource, AngleEvent, TemperatureEvent
import threading
import time

# ========== 顶部配置区 ==========
HAND_SIDE = "left"  # 切左右手
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
MOTOR_SPEED = 20
ACTION_WAIT = 3
ANGLE_POLL_INTERVAL = 0.1  # 角度轮询间隔（秒），0.1 = 10Hz
STREAM_PRINT_EVERY = 1    # 每收到 N 次角度事件打印一次
# ========================================================

# 关节顺序与取值范围（0~100）：
# [thumb_flex, thumb_abd, index, middle, ring, pinky]

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
hand_name = "左手" if HAND_SIDE == "left" else "右手"


def run_action(hand, pose, action_name="", wait=None):
    """发送动作指令并等待，角度由主线程流式读取并打印。"""
    if action_name:
        print(f"\n--- {action_name} ---")
    hand.angle.set_angles(pose)
    time.sleep(wait if wait is not None else ACTION_WAIT)


def run_movement_sequence(hand, done_event: threading.Event):
    """在后台线程中执行完整动作序列。"""
    try:
        run_action(hand, poses["open"], "初始状态：全张开")
        run_action(hand, poses["semi_open"], "测试数据类控制：半张开")
        run_action(hand, poses["open"], "回到全张开")
        run_action(hand, poses["fist_list"], "测试列表控制：轻握拳")
        run_action(hand, poses["open"], "回到全张开")
        print("\n✅ 动作序列完成")
    except Exception as e:
        print(f"\n❌ 动作线程出错：{type(e).__name__}: {e}")
    finally:
        done_event.set()


def go_to_safe(hand):
    """回到全张开安全位。"""
    print("\n🔒 自动回到全张开安全位...")
    hand.angle.set_angles(poses["open"])
    time.sleep(ACTION_WAIT)
    angle_data = hand.angle.get_blocking(timeout_ms=1000)
    angle = [round(x, 2) for x in angle_data.angles.to_list()]
    print(f"安全位角度: {angle}")


if __name__ == "__main__":
    print(f"=== 运动 + 流式读角测试（{hand_name}） ===")

    with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        print("关闭默认轮询，避免队列堵塞...")
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)

        hand.speed.set_speeds([MOTOR_SPEED] * 6)
        print(f"已设置低速模式：{MOTOR_SPEED}")

        print(f"开启角度轮询（{1 / ANGLE_POLL_INTERVAL:.0f}Hz）...")
        hand.start_polling({SensorSource.ANGLE: ANGLE_POLL_INTERVAL})

        movement_done = threading.Event()
        movement_thread = threading.Thread(
            target=run_movement_sequence,
            args=(hand, movement_done),
            name="movement",
            daemon=True,
        )

        angle_count = 0
        temp_count = 0
        movement_error = None

        try:
            print("启动动作线程，同时开始流式读取角度...\n")
            movement_thread.start()

            for event in hand.stream():
                match event:
                    case AngleEvent(data=data):
                        angle_count += 1
                        if angle_count % STREAM_PRINT_EVERY == 0:
                            angle_list = [round(x, 2) for x in data.angles.to_list()]
                            print(f"[流式] 角度: {angle_list}")

                    case TemperatureEvent(data=data):
                        temp_count += 1
                        temp_list = [round(x, 2) for x in data.temperatures.to_list()]
                        print(f"[流式] 温度: {temp_list} ℃")

                if movement_done.is_set():
                    break

            movement_thread.join(timeout=5)
            if movement_thread.is_alive():
                print("⚠️  动作线程未在预期时间内结束")

        except Exception as e:
            movement_error = e
            print(f"\n❌ 测试出错：{type(e).__name__}: {e}")
        finally:
            hand.stop_polling()
            hand.stop_stream()
            print("已停止轮询和流式读取")

            try:
                go_to_safe(hand)
            except Exception as e:
                print(f"⚠️  回到安全位失败：{e}")

        print(
            f"\n运行结束，共收到角度事件 {angle_count} 次，温度事件 {temp_count} 次"
        )
        if movement_error is None and movement_done.is_set():
            print("✅ 测试完成")
