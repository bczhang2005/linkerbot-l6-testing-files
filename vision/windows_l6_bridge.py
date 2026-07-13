"""
Windows + PCAN + L6 桥接：同时提供
  - :7080  GET /api/hand/devices   （给浏览器）
  - :5260  POST /api/can           （给 dexterous-hand-rps/server.go）

依赖：conda activate linkerbot
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"
MOTOR_SPEED = 50
LOGICAL_INTERFACE = "can0"  # 网页/Go 侧使用的逻辑接口名，映射到 PCAN

# 与 6.gameplay/app.js 中 O6/L6 预设 CAN data 对应
GESTURE_BY_DATA = {
    tuple([1, 65, 170, 25, 25, 25, 25]): "ROCK",
    tuple([1, 255, 255, 255, 255, 255, 255]): "PAPER",
    tuple([1, 65, 180, 255, 255, 25, 25]): "SCISSORS",
}

# 与 testing/poses/pose_*.py 左手的姿势一致（0~100）
POSES = {
    "left": {
        "ROCK": L6Angle(thumb_flex=20, thumb_abd=20, index=55, middle=50, ring=50, pinky=50),
        "PAPER": L6Angle(thumb_flex=100, thumb_abd=100, index=100, middle=100, ring=100, pinky=100),
        "SCISSORS": L6Angle(thumb_flex=25, thumb_abd=30, index=100, middle=100, ring=22, pinky=18),
    },
}

hand: Optional[L6] = None
hand_lock = threading.Lock()
_follow_log_counter = 0


def expected_can_id() -> int:
    return 0x28 if HAND_SIDE == "left" else 0x27


def can_follow_data_to_l6_angle(data: list[int]) -> Optional[L6Angle]:
    """跟随模式：7 字节 finger 帧 → L6Angle（与 4.follow-me scale255 互逆）。"""
    if len(data) != 7 or data[0] != 1:
        return None

    def byte_to_angle(value: int) -> int:
        return max(0, min(100, round(value * 100 / 255)))

    return L6Angle(
        thumb_flex=byte_to_angle(data[1]),
        thumb_abd=byte_to_angle(data[2]),
        index=byte_to_angle(data[3]),
        middle=byte_to_angle(data[4]),
        ring=byte_to_angle(data[5]),
        pinky=byte_to_angle(data[6]),
    )


def init_hand() -> None:
    global hand
    print(f"[init] 连接 L6 {HAND_SIDE} @ {INTERFACE} ...")
    hand = L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE)
    hand.__enter__()
    hand.stop_polling()
    hand.stop_stream()
    hand.speed.set_speeds([MOTOR_SPEED] * 6)
    print("[init] L6 已连接")


def execute_can_payload(can_id: int, data: list[int]) -> bool:
    global _follow_log_counter

    want_id = expected_can_id()
    if can_id != want_id:
        print(f"[warn] CAN id {can_id:#x} 与 HAND_SIDE={HAND_SIDE} 期望 {want_id:#x}")

    key = tuple(data)
    gesture = GESTURE_BY_DATA.get(key)
    if gesture is not None:
        pose = POSES[HAND_SIDE][gesture]
        with hand_lock:
            hand.angle.set_angles(pose)
        print(f"[can] id={can_id:#x} -> {gesture}")
        return True

    follow_pose = can_follow_data_to_l6_angle(data)
    if follow_pose is not None:
        with hand_lock:
            hand.angle.set_angles(follow_pose)
        _follow_log_counter += 1
        if _follow_log_counter % 30 == 1:
            print(
                f"[follow] id={can_id:#x} "
                f"thumb=({follow_pose.thumb_flex},{follow_pose.thumb_abd}) "
                f"idx={follow_pose.index} mid={follow_pose.middle} "
                f"ring={follow_pose.ring} pinky={follow_pose.pinky}"
            )
        return True

    print(f"[warn] 未知 CAN data: {data}")
    return False


class DeviceHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[7080] {self.address_string()} {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path != "/api/hand/devices":
            self.send_error(404)
            return
        body = {
            "status": "ok",
            "data": [{
                "model": "L6",
                "interface": LOGICAL_INTERFACE,
                "side": HAND_SIDE,
                "variant": "",
            }],
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(payload)


class CanHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[5260] {self.address_string()} {fmt % args}")

    def do_GET(self):
        if self.path in ("/api/health", "/api/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/can":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            msg = json.loads(self.rfile.read(length))
            iface = msg.get("interface", "")
            can_id = int(msg.get("id", 0))
            data = [int(x) for x in msg.get("data", [])]
            if iface != LOGICAL_INTERFACE:
                print(f"[warn] interface={iface}, 期望 {LOGICAL_INTERFACE}")
            ok = execute_can_payload(can_id, data)
            resp = {"status": "success" if ok else "error"}
            code = 200 if ok else 500
        except Exception as e:
            resp = {"status": "error", "message": str(e)}
            code = 500
        payload = json.dumps(resp).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)


def serve(port: int, handler):
    HTTPServer(("0.0.0.0", port), handler).serve_forever()


if __name__ == "__main__":
    init_hand()
    threading.Thread(target=serve, args=(7080, DeviceHandler), daemon=True).start()
    threading.Thread(target=serve, args=(5260, CanHandler), daemon=True).start()
    print("Windows L6 桥接已启动")
    print("  设备配置: http://localhost:7080/api/hand/devices")
    print("  CAN 转发: http://localhost:5260/api/can")
    print("按 Ctrl+C 退出")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        if hand is not None:
            hand.__exit__(None, None, None)