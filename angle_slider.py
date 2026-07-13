"""
angle_slider.py

【测试目的】
  Tkinter 滑条 GUI：6 路关节 0~100 实时控制，拖动即发送 set_angles，并显示实际角度反馈。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确
  · 须 stop 默认轮询后再开角度流式读

【操作步骤】
  1. 修改 HAND_SIDE、MOVE_SPEED 等配置
  2. 执行：python angle_slider.py
  3. 拖动各滑条；可用「全张开/全收」快捷按钮
  4. 关闭窗口自动回安全位

【预期结果】
  · 滑条拖动时手指跟随变化，右侧显示实际角度
  · 关闭后回到全张开并断开连接

【实际结果】
  （测试后在此填写）

【说明】
  · MOVE_SPEED 越小越慢；SEND_DELAY_MS 控制拖动时节流间隔
  · 关节顺序：[thumb_flex, thumb_abd, index, middle, ring, pinky]
"""

import tkinter as tk
from tkinter import messagebox
import sys
import threading
import time
from linkerbot import L6
from linkerbot.hand.l6 import SensorSource, AngleEvent
from linkerbot.exceptions import TimeoutError as LinkerTimeoutError

# ========== 配置区 ==========
HAND_SIDE = "right"        # "left" / "right"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
MOVE_SPEED = 20            # 运动速度
ANGLE_POLL_INTERVAL = 0.1  # 角度反馈轮询（秒）
SEND_DELAY_MS = 80         # 滑条拖动时发送间隔（毫秒），避免指令过密
UPDATE_INTERVAL = 50       # 界面刷新间隔（毫秒）
READ_TIMEOUT_MS = 3000    # 验证灵巧手是否在线的超时（毫秒）
POLLING_SETTLE_SEC = 1.0   # stop_polling 后等待时间
# ============================================================

JOINT_NAMES = [
    "拇指弯曲 (thumb_flex)",
    "拇指侧摆 (thumb_abd)",
    "食指 (index)",
    "中指 (middle)",
    "无名指 (ring)",
    "小指 (pinky)",
]

# 滑条初始值（0~100）
INITIAL_ANGLES = [100, 100, 100, 100, 100, 100]

running = True
hand = None
latest_angles = list(INITIAL_ANGLES)
pending_send_id = None


def verify_hand_communication(hand):
    """验证灵巧手是否在 CAN 上应答（L6 初始化仅表示 PCAN 通道已开）。"""
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(POLLING_SETTLE_SEC)

    try:
        data = hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS)
        return True, [round(x, 2) for x in data.angles.to_list()]
    except LinkerTimeoutError:
        pass

    hand.start_polling({SensorSource.ANGLE: ANGLE_POLL_INTERVAL})
    time.sleep(1.0)
    try:
        data = hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS)
        return True, [round(x, 2) for x in data.angles.to_list()]
    except LinkerTimeoutError:
        return False, None


def connect_hand(preferred_side):
    """连接并验证灵巧手；失败时自动尝试另一只手。"""
    sides_to_try = [preferred_side]
    other = "left" if preferred_side == "right" else "right"
    sides_to_try.append(other)

    last_error = "灵巧手无应答（请检查是否上电、CAN 线、HAND_SIDE）"
    for side in sides_to_try:
        side_name = "左手" if side == "left" else "右手"
        print(f"正在打开 CAN 并验证灵巧手（{side_name} / {side}）...")
        hand = None
        ok = False
        try:
            hand = L6(
                side=side,
                interface_name=INTERFACE,
                interface_type=INTERFACE_TYPE,
            )
            print("   PCAN 通道已打开，正在读角度验证通信...")
            ok, angles = verify_hand_communication(hand)
            if ok:
                if side != preferred_side:
                    print(f"💡 当前 HAND_SIDE 应为 \"{side}\"，不是 \"{preferred_side}\"")
                print(f"✅ 灵巧手通信正常，角度: {angles}")
                return hand, side, angles
            last_error = f"{side_name} 无应答（{READ_TIMEOUT_MS} ms 超时）"
            print(f"❌ {last_error}")
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            print(f"❌ 连接失败: {last_error}")
        finally:
            if hand is not None and not ok:
                try:
                    hand.close()
                except Exception:
                    pass

    raise RuntimeError(last_error)


def prepare_hand_runtime(hand):
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(0.5)
    hand.start_polling({SensorSource.ANGLE: ANGLE_POLL_INTERVAL})
    hand.speed.set_speeds([MOVE_SPEED] * 6)


def read_angle_thread():
    """后台读取实际角度，用于界面反馈。"""
    global latest_angles, running
    try:
        for event in hand.stream():
            if not running:
                break
            if isinstance(event, AngleEvent):
                latest_angles = [round(x, 1) for x in event.data.angles.to_list()]
    except Exception as e:
        print(f"读取线程出错: {e}")


def get_slider_angles(sliders):
    return [int(round(s.get())) for s in sliders]


def send_angles_now(sliders, status_label):
    """立即发送当前滑条角度。"""
    global hand, running
    if not running or hand is None:
        return
    angles = get_slider_angles(sliders)
    try:
        hand.angle.set_angles(angles)
        status_label.config(
            text=f"✅ 已发送: {angles}",
            fg="#16a34a",
        )
    except Exception as e:
        status_label.config(text=f"❌ 发送失败: {e}", fg="#dc2626")


def schedule_send(root, sliders, status_label):
    """拖动滑条时节流发送。"""
    global pending_send_id

    if pending_send_id is not None:
        root.after_cancel(pending_send_id)

    def _do_send():
        global pending_send_id
        pending_send_id = None
        send_angles_now(sliders, status_label)

    pending_send_id = root.after(SEND_DELAY_MS, _do_send)


def on_slider_change(root, sliders, value_labels, feedback_labels, index, status_label):
    value_labels[index].config(text=f"{int(float(sliders[index].get()))}")
    schedule_send(root, sliders, status_label)


def update_feedback(feedback_labels):
    global latest_angles, running
    if not running:
        return
    for i, label in enumerate(feedback_labels):
        label.config(text=f"实际 {latest_angles[i]}")
    root.after(UPDATE_INTERVAL, update_feedback, feedback_labels)


def set_all_sliders(sliders, value_labels, values, status_label):
    for i, val in enumerate(values):
        sliders[i].set(val)
        value_labels[i].config(text=f"{int(val)}")
    send_angles_now(sliders, status_label)


def on_closing(root, sliders, status_label):
    global running, hand, pending_send_id
    print("正在关闭，回到全张开安全位...")
    running = False
    if pending_send_id is not None:
        root.after_cancel(pending_send_id)
    time.sleep(0.2)
    try:
        hand.angle.set_angles([100, 100, 100, 100, 100, 100])
        time.sleep(1)
        hand.stop_polling()
        hand.stop_stream()
        hand.close()
        print("已回到安全位，连接已断开")
    except Exception as e:
        print(f"清理出错: {e}")
    root.destroy()


if __name__ == "__main__":
    print("正在连接灵巧手...")

    try:
        hand, HAND_SIDE, _initial_angles = connect_hand(HAND_SIDE)
        hand_name = "右手" if HAND_SIDE == "right" else "左手"
        prepare_hand_runtime(hand)
        print(f"✅ 已连接（{hand_name}），启动滑条控制...")
    except Exception as e:
        print(f"\n❌ 无法连接灵巧手: {e}")
        err_root = tk.Tk()
        err_root.withdraw()
        messagebox.showerror(
            "连接失败",
            f"PCAN 可能已就绪，但灵巧手通信失败：\n\n{e}\n\n"
            "请检查：\n"
            "· 灵巧手是否上电\n"
            "· CAN 线是否接好\n"
            "· HAND_SIDE 是否与实物一致\n"
            "· 是否关闭 PCAN-View 等占用程序",
        )
        err_root.destroy()
        sys.exit(1)

    root = tk.Tk()
    root.title(f"L6 滑条控制 - {hand_name}")
    root.geometry("520x720")
    root.minsize(480, 680)
    root.configure(bg="#f0f0f0")

    status_label = tk.Label(
        root, text=f"✅ 已连接（{hand_name}）— 拖动滑条实时控制各指角度 (0~100)",
        font=("微软雅黑", 10), fg="#16a34a", bg="#f0f0f0", pady=10,
    )
    status_label.pack(side="bottom", fill="x")

    content = tk.Frame(root, bg="#f0f0f0")
    content.pack(fill="both", expand=True, padx=20, pady=10)

    tk.Label(
        content, text="L6 灵巧手 — 滑条控制",
        font=("微软雅黑", 16, "bold"), bg="#f0f0f0", pady=8,
    ).pack()

    tk.Label(
        content,
        text="拖动滑条即可实时控制各指角度 (0~100)",
        font=("微软雅黑", 9), fg="#666666", bg="#f0f0f0",
    ).pack(pady=(0, 10))

    sliders = []
    value_labels = []
    feedback_labels = []

    for i, name in enumerate(JOINT_NAMES):
        row = tk.Frame(content, bg="#f0f0f0", pady=8)
        row.pack(fill="x")

        tk.Label(row, text=name, font=("微软雅黑", 10), bg="#f0f0f0", width=22, anchor="w").pack(side="left")

        val_label = tk.Label(row, text=str(INITIAL_ANGLES[i]), font=("Consolas", 12, "bold"),
                             fg="#2563eb", bg="#f0f0f0", width=4)
        val_label.pack(side="right", padx=(8, 0))
        value_labels.append(val_label)

        fb_label = tk.Label(row, text="实际 --", font=("Consolas", 9),
                            fg="#64748b", bg="#f0f0f0", width=10)
        fb_label.pack(side="right")
        feedback_labels.append(fb_label)

        slider = tk.Scale(
            row,
            from_=0, to=100,
            orient="horizontal",
            length=220,
            resolution=1,
            showvalue=False,
            bg="#f0f0f0",
            highlightthickness=0,
            troughcolor="#dbeafe",
            activebackground="#2563eb",
        )
        slider.set(INITIAL_ANGLES[i])
        slider.pack(side="left", fill="x", expand=True, padx=8)
        slider.bind(
            "<ButtonRelease-1>",
            lambda e, s=sliders, sl=status_label: send_angles_now(s, sl),
        )
        slider.configure(
            command=lambda v, idx=i: on_slider_change(
                root, sliders, value_labels, feedback_labels, idx, status_label
            )
        )
        sliders.append(slider)

    btn_row = tk.Frame(content, bg="#f0f0f0", pady=12)
    btn_row.pack(fill="x")

    tk.Button(
        btn_row, text="全张开 (100)",
        font=("微软雅黑", 10),
        bg="#e2e8f0", fg="#1e293b", relief="flat", padx=8, pady=4,
        command=lambda: set_all_sliders(sliders, value_labels, [100] * 6, status_label),
    ).pack(side="left", padx=4)

    tk.Button(
        btn_row, text="全收 (0)",
        font=("微软雅黑", 10),
        bg="#fee2e2", fg="#991b1b", relief="flat", padx=8, pady=4,
        command=lambda: set_all_sliders(sliders, value_labels, [0] * 6, status_label),
    ).pack(side="left", padx=4)

    root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root, sliders, status_label))

    read_thread = threading.Thread(target=read_angle_thread, daemon=True)
    read_thread.start()

    root.after(300, lambda: send_angles_now(sliders, status_label))
    update_feedback(feedback_labels)

    root.mainloop()
