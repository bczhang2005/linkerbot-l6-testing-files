"""
angle_monitor.py

【测试目的】
  Tkinter 调试控制台：流式显示 6 路角度，快捷姿势按钮 + 自定义角度输入发送指令。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确
  · 须 stop 默认轮询（脚本内已处理）

【操作步骤】
  1. 修改 HAND_SIDE、PRESET_POSES、MOVE_SPEED
  2. 执行：python angle_monitor.py
  3. 观察实时角度；点快捷姿势或输入逗号分隔 6 值后发送
  4. 关闭窗口回安全位

【预期结果】
  · 角度数值持续刷新；按钮/输入发送后手指运动，状态栏提示已发送

【实际结果】
  （测试后在此填写）

【说明】
  · PRESET_POSES 字典增删即可改快捷按钮
  · 示例输入：100,70,30,30,30,30
"""

import tkinter as tk
from tkinter import messagebox
import threading
import time
import json
import os
from linkerbot import L6
from linkerbot.hand.l6 import SensorSource, AngleEvent
from linkerbot.exceptions import TimeoutError as LinkerTimeoutError

# #region agent log
_DEBUG_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-be4fdb.log")
def _dbg(hypothesis_id, location, message, data=None, run_id="pre-fix"):
    import time as _t
    payload = {
        "sessionId": "be4fdb",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(_t.time() * 1000),
    }
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            _f.flush()
            os.fsync(_f.fileno())
    except Exception as exc:
        print(f"[debug log failed] {exc}", flush=True)
    print(f"[angle_monitor] {message}: {payload['data']}", flush=True)
# #endregion

# ========== 配置区 ==========
HAND_SIDE = "left"        # 左手改 "left"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
ANGLE_POLL_INTERVAL = 0.1  # 角度轮询频率
UPDATE_INTERVAL = 50       # 界面刷新间隔（毫秒）
MOVE_SPEED = 10            # 运动速度，保持低速安全
READ_TIMEOUT_MS = 3000    # 验证灵巧手是否在线的超时（毫秒）
POLLING_SETTLE_SEC = 1.0   # stop_polling 后等待时间
# ============================================================

# ========== 新增：预设姿势（点按钮一键执行） ==========
PRESET_POSES = {
    "全张开": [100, 100, 100, 100, 100, 100],
    "半张开": [70, 70, 70, 70, 70, 70],
    "轻握拳": [60, 20, 30, 30, 30, 30],  # 右手安全参数，左手可调
}
# ============================================================

# 全局变量
latest_angles = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
running = True
hand = None  # 把hand提成全全局，方便按钮回调里用

# 关节名称
JOINT_NAMES = [
    "拇指弯曲 (thumb_flex)",
    "拇指侧摆 (thumb_abd)",
    "食指 (index)",
    "中指 (middle)",
    "无名指 (ring)",
    "小指 (pinky)"
]


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
    """验证通过后，按本程序需求配置轮询与速度。"""
    hand.stop_polling()
    hand.stop_stream()
    time.sleep(0.5)
    hand.start_polling({SensorSource.ANGLE: ANGLE_POLL_INTERVAL})
    hand.speed.set_speeds([MOVE_SPEED] * 6)


def read_angle_thread():
    """子线程：流式读取角度"""
    global latest_angles, running
    try:
        for event in hand.stream():
            if not running:
                break
            if isinstance(event, AngleEvent):
                latest_angles = [round(x, 1) for x in event.data.angles.to_list()]
    except Exception as e:
        print(f"读取线程出错: {e}")


def update_ui(labels, status_label):
    """主线程：刷新界面"""
    global latest_angles, running
    if not running:
        return
    for i, label in enumerate(labels):
        label.config(text=f"{latest_angles[i]} %")
    root.after(UPDATE_INTERVAL, update_ui, labels, status_label)


def send_angles(angle_list, pose_name="自定义", status_label=None):
    """发送角度指令，带校验和状态提示"""
    global hand, running
    if not running:
        return
    if status_label is None:
        raise RuntimeError("status_label 未初始化")

    try:
        # 校验：必须是6个数字，范围0-100
        if len(angle_list) != 6:
            messagebox.showwarning("输入错误", "必须输入6个角度，用逗号（英文）分隔！")
            return
        for a in angle_list:
            if not (0 <= a <= 100):
                messagebox.showwarning("输入错误", "角度必须在0-100之间！")
                return

        # 发指令
        hand.angle.set_angles(angle_list)
        status_label.config(text=f"✅ 已发送：{pose_name}", fg="#16a34a")
    except Exception as e:
        status_label.config(text=f"❌ 发送失败：{e}", fg="#dc2626")


# ========== 输入框按回车触发的函数 ==========
def on_enter_press(event, entry, status_label):
    input_text = entry.get().strip()
    try:
        # 把输入的字符串转成数字列表，支持逗号、空格分隔
        angle_list = [float(x.strip()) for x in input_text.replace(" ", "").split(",")]
        send_angles(angle_list, "自定义指令", status_label)
        entry.delete(0, tk.END)  # 发完清空输入框
    except ValueError:
        messagebox.showwarning("输入错误", "请输入数字，用逗号分隔！")


# ========== 快捷按钮点击的函数 ==========
def on_preset_click(pose_name, status_label):
    angle_list = PRESET_POSES[pose_name]
    send_angles(angle_list, pose_name, status_label)


def on_closing():
    """关窗口清理：回安全位、断连接"""
    global running, hand
    print("正在关闭，回到安全位...")
    running = False
    try:
        root.unbind_all("<MouseWheel>")
    except Exception:
        pass
    time.sleep(0.3)
    
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
    # #region agent log
    _dbg("A", "angle_monitor.py:main", "script_start", {"preset_count": len(PRESET_POSES), "preset_keys": list(PRESET_POSES.keys())})
    # #endregion

    try:
        hand, HAND_SIDE, _initial_angles = connect_hand(HAND_SIDE)
        hand_name = "左手" if HAND_SIDE == "left" else "右手"
        prepare_hand_runtime(hand)
        print(f"✅ 已连接（{hand_name}），启动监控...")
        # #region agent log
        _dbg("A", "angle_monitor.py:main", "l6_init_ok", {"hand_side": HAND_SIDE})
        # #endregion
    except Exception as e:
        # #region agent log
        _dbg("A", "angle_monitor.py:main", "l6_init_failed", {"error": f"{type(e).__name__}: {e}"})
        # #endregion
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
        raise SystemExit(1)

    # 启动读角度子线程（GUI 就绪后再读，避免初始化阶段干扰界面）
    def start_read_thread():
        read_thread = threading.Thread(target=read_angle_thread, daemon=True)
        read_thread.start()
        # #region agent log
        _dbg("F", "angle_monitor.py:main", "read_thread_started", run_id="post-fix")
        # #endregion

    # ========== 建界面 ==========
    root = tk.Tk()
    root.title(f"L6 调试控制台 - {hand_name}")
    root.geometry("420x680")
    root.minsize(420, 680)
    root.configure(bg="#f0f0f0")

    status_label = tk.Label(
        root, text=f"✅ 已连接（{hand_name}）— 拖动/按钮控制各指角度",
        font=("微软雅黑", 10),
        fg="#16a34a", bg="#f0f0f0", pady=12
    )
    status_label.pack(side="bottom", fill="x")

    body = tk.Frame(root, bg="#f0f0f0")
    body.pack(side="top", fill="both", expand=True)

    canvas = tk.Canvas(body, bg="#f0f0f0", highlightthickness=0)
    scrollbar = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
    content = tk.Frame(canvas, bg="#f0f0f0")
    content.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    def _resize_canvas(event):
        canvas.itemconfigure(canvas_window, width=event.width)

    canvas.bind("<Configure>", _resize_canvas)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    root.bind_all("<MouseWheel>", _on_mousewheel)

    # 标题
    tk.Label(
        content, text="L6 灵巧手 调试控制台",
        font=("微软雅黑", 16, "bold"),
        bg="#f0f0f0", pady=12
    ).pack()

    # 角度显示区
    angle_frame = tk.Frame(content, bg="#f0f0f0")
    angle_frame.pack(fill="x", padx=30, pady=5)
    
    angle_labels = []
    for name in JOINT_NAMES:
        row = tk.Frame(angle_frame, bg="#f0f0f0", pady=5)
        row.pack(fill="x")
        tk.Label(row, text=name, font=("微软雅黑", 10), bg="#f0f0f0", anchor="w").pack(side="left")
        val_label = tk.Label(
            row, text="0 %", font=("Consolas", 13, "bold"),
            fg="#2563eb", bg="#f0f0f0", width=6, anchor="e"
        )
        val_label.pack(side="right")
        angle_labels.append(val_label)

    # 分割线
    tk.Frame(content, height=1, bg="#dddddd").pack(fill="x", padx=20, pady=10)

    # ========== 快捷按钮区（带边框，便于确认已生成） ==========
    preset_frame = tk.LabelFrame(
        content,
        text=" 快捷姿势 ",
        font=("微软雅黑", 11, "bold"),
        bg="#f0f0f0",
        fg="#1e3a8a",
        padx=12,
        pady=10,
    )
    preset_frame.pack(fill="x", padx=20, pady=8)

    btn_frame = tk.Frame(preset_frame, bg="#f0f0f0")
    btn_frame.pack(fill="x")

    # 动态生成快捷按钮，加预设就改上面的 PRESET_POSES 字典就行
    preset_btn_count = 0
    # #region agent log
    _dbg("B", "angle_monitor.py:btn_loop", "before_button_loop", {"preset_keys": list(PRESET_POSES.keys())})
    # #endregion
    for pose_name in PRESET_POSES.keys():
        try:
            btn = tk.Button(
                btn_frame, text=pose_name,
                font=("微软雅黑", 10, "bold"),
                width=9, height=2,
                bg="#3b82f6", fg="white",
                activebackground="#2563eb", activeforeground="white",
                relief="raised", bd=2,
                command=lambda name=pose_name, sl=status_label: on_preset_click(name, sl)
            )
            btn.pack(side="left", padx=6, pady=4, ipadx=4)
            preset_btn_count += 1
            # #region agent log
            _dbg("C", "angle_monitor.py:btn_loop", "button_created", {"pose_name": pose_name, "index": preset_btn_count})
            # #endregion
        except Exception as e:
            # #region agent log
            _dbg("C", "angle_monitor.py:btn_loop", "button_create_failed", {"pose_name": pose_name, "error": f"{type(e).__name__}: {e}"})
            # #endregion
            raise
    # #region agent log
    _dbg("B", "angle_monitor.py:btn_loop", "after_button_loop", {"preset_btn_count": preset_btn_count})
    # #endregion

    # 分割线
    tk.Frame(content, height=1, bg="#dddddd").pack(fill="x", padx=20, pady=10)

    # ========== 自定义输入区 ==========
    tk.Label(
        content, text="自定义角度（6个值，逗号分隔）",
        font=("微软雅黑", 11, "bold"),
        bg="#f0f0f0", pady=5
    ).pack()

    input_frame = tk.Frame(content, bg="#f0f0f0")
    input_frame.pack(pady=5)

    angle_entry = tk.Entry(
        input_frame, font=("Consolas", 11),
        width=28, justify="center"
    )
    angle_entry.pack(side="left", padx=5)
    # 按回车发送
    angle_entry.bind(
        "<Return>",
        lambda e, entry=angle_entry, sl=status_label: on_enter_press(e, entry, sl)
    )

    send_btn = tk.Button(
        input_frame, text="发送",
        font=("微软雅黑", 10),
        width=6, height=1,
        bg="#2563eb", fg="white",
        relief="flat",
        command=lambda entry=angle_entry, sl=status_label: on_enter_press(None, entry, sl)
    )
    send_btn.pack(side="left", padx=5)

    # 输入提示
    tk.Label(
        content, text="示例：100,70,30,30,30,30  （按回车发送）",
        font=("微软雅黑", 8),
        fg="#666666", bg="#f0f0f0", pady=3
    ).pack()

    # 绑定关闭事件
    root.protocol("WM_DELETE_WINDOW", on_closing)

    def _log_layout_after_idle():
        root.update_idletasks()
        win_h = root.winfo_height()
        req_h = content.winfo_reqheight()
        btn_y = btn_frame.winfo_y()
        btn_h = btn_frame.winfo_height()
        btn_w = btn_frame.winfo_width()
        child_count = len(btn_frame.winfo_children())
        # #region agent log
        _dbg("D", "angle_monitor.py:layout", "layout_metrics", {
            "log_path": _DEBUG_LOG,
            "window_height": win_h,
            "content_req_height": req_h,
            "overflow": req_h > win_h,
            "btn_frame_y": btn_y,
            "btn_frame_h": btn_h,
            "btn_frame_w": btn_w,
            "btn_frame_children": child_count,
            "btn_mapped": [c.winfo_ismapped() for c in btn_frame.winfo_children()],
            "btn_heights": [c.winfo_height() for c in btn_frame.winfo_children()],
            "btn_texts": [c.cget("text") for c in btn_frame.winfo_children()],
            "preset_btn_count": preset_btn_count,
            "status_label_exists": status_label.winfo_exists(),
        }, run_id="post-fix")
        # #endregion

    # 启动界面刷新
    update_ui(angle_labels, status_label)
    root.after(100, start_read_thread)
    root.after(500, _log_layout_after_idle)

    # 运行主循环
    root.mainloop()