"""
RealSense D405 方案 B：Color + Depth → 21 点 3D 手系 → WebSocket 推送

供 dexterous-hand-rps/7.follow-me-3d 页面消费。

用法：
  pip install -r hand_tracking_requirements.txt
  python hand_tracking_service.py

WebSocket: ws://localhost:8765
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
import pyrealsense2 as rs
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision
from websockets.asyncio.server import serve

WS_HOST = "localhost"
WS_PORT = 8765
COLOR_W = 640
COLOR_H = 480
COLOR_FPS = 30
PREVIEW_W = 640
PREVIEW_H = 480
PREVIEW_EVERY_N = 1
DEPTH_PATCH = 5
HANDS_HOLD_S = 0.25
LANDMARK_2D_SMOOTH = 0.45

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]
HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
# MediaPipe C++ 在 Windows 上无法打开含中文等非 ASCII 路径，模型须放在纯英文目录。
HAND_MODEL_CACHE = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "dexterous-hand-rps"
    / "hand_landmarker.task"
)
MIN_MODEL_BYTES = 1_000_000


def ensure_hand_model() -> str:
    HAND_MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)

    if HAND_MODEL_CACHE.is_file() and HAND_MODEL_CACHE.stat().st_size >= MIN_MODEL_BYTES:
        return str(HAND_MODEL_CACHE)

    legacy = Path(__file__).with_name("hand_landmarker.task")
    if legacy.is_file() and legacy.stat().st_size >= MIN_MODEL_BYTES:
        shutil.copy2(legacy, HAND_MODEL_CACHE)
        print(f"[tracker] 已从脚本目录复制模型 → {HAND_MODEL_CACHE}")
        return str(HAND_MODEL_CACHE)

    print("[tracker] 正在下载 hand_landmarker.task …")
    tmp = HAND_MODEL_CACHE.with_suffix(".task.download")
    urllib.request.urlretrieve(HAND_MODEL_URL, tmp)
    if not tmp.is_file() or tmp.stat().st_size < MIN_MODEL_BYTES:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            "模型下载失败或文件过小，请检查网络后重试。"
            f" 期望 ≥ {MIN_MODEL_BYTES} 字节。"
        )
    tmp.replace(HAND_MODEL_CACHE)
    print(f"[tracker] 模型已缓存: {HAND_MODEL_CACHE}")
    return str(HAND_MODEL_CACHE)


class RealSenseHandTracker:
    def __init__(self) -> None:
        model_path = ensure_hand_model()
        options = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)
        self._video_ts_ms = 0

        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, COLOR_W, COLOR_H, rs.format.bgr8, COLOR_FPS)
        config.enable_stream(rs.stream.depth, COLOR_W, COLOR_H, rs.format.z16, COLOR_FPS)
        profile = self.pipeline.start(config)

        align_to = rs.stream.color
        self.align = rs.align(align_to)

        color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
        intr = color_stream.get_intrinsics()
        self.fx = intr.fx
        self.fy = intr.fy
        self.ppx = intr.ppx
        self.ppy = intr.ppy

        self._frame_count = 0
        self._last_fps_time = time.time()
        self._fps = 0.0
        self._smooth_2d: dict[str, list[dict[str, float]]] = {}
        self._last_hands_draw: list[dict[str, Any]] = []
        self._last_hands_draw_t = 0.0

    def close(self) -> None:
        self.landmarker.close()
        self.pipeline.stop()

    def _sample_depth_m(self, depth_frame, u: int, v: int) -> float | None:
        h, w = depth_frame.get_height(), depth_frame.get_width()
        half = DEPTH_PATCH // 2
        values: list[float] = []
        for dy in range(-half, half + 1):
            for dx in range(-half, half + 1):
                x = int(np.clip(u + dx, 0, w - 1))
                y = int(np.clip(v + dy, 0, h - 1))
                d = depth_frame.get_distance(x, y)
                if d > 0.05:
                    values.append(d)
        if not values:
            return None
        return float(np.median(values))

    def _backproject(self, u: float, v: float, depth_m: float) -> np.ndarray:
        x = (u - self.ppx) * depth_m / self.fx
        y = (v - self.ppy) * depth_m / self.fy
        z = depth_m
        return np.array([x, y, z], dtype=np.float64)

    def _to_hand_frame(self, points_cam: np.ndarray) -> np.ndarray:
        """手腕为原点，以腕→中指 MCP 距离归一化，并对齐掌面坐标系。"""
        wrist = points_cam[0]
        rel = points_cam - wrist
        scale = np.linalg.norm(points_cam[9] - points_cam[0])
        if scale < 1e-5:
            scale = 1.0
        rel /= scale

        y_axis = rel[9].copy()
        yn = np.linalg.norm(y_axis)
        if yn < 1e-8:
            y_axis = np.array([0.0, 1.0, 0.0])
        else:
            y_axis /= yn

        x_raw = rel[5] - rel[17]
        x_axis = x_raw - np.dot(x_raw, y_axis) * y_axis
        xn = np.linalg.norm(x_axis)
        if xn < 1e-8:
            x_axis = np.array([1.0, 0.0, 0.0])
        else:
            x_axis /= xn

        z_axis = np.cross(x_axis, y_axis)
        zn = np.linalg.norm(z_axis)
        if zn < 1e-8:
            z_axis = np.array([0.0, 0.0, 1.0])
        else:
            z_axis /= zn

        rot = np.stack([x_axis, y_axis, z_axis], axis=0)
        aligned = (rot @ rel.T).T
        return aligned

    def _smooth_landmarks2d(
        self, label: str, points: list[dict[str, float]]
    ) -> list[dict[str, float]]:
        prev = self._smooth_2d.get(label)
        if not prev:
            self._smooth_2d[label] = points
            return points
        alpha = LANDMARK_2D_SMOOTH
        out = [
            {
                "x": alpha * p["x"] + (1.0 - alpha) * prev[i]["x"],
                "y": alpha * p["y"] + (1.0 - alpha) * prev[i]["y"],
            }
            for i, p in enumerate(points)
        ]
        self._smooth_2d[label] = out
        return out

    def _depth_to_bgr(self, depth_m: float) -> tuple[int, int, int]:
        """近=黄，远=蓝（深度着色，与 2D 固定色不同）。"""
        near, far = 0.20, 0.60
        t = max(0.0, min(1.0, (depth_m - near) / (far - near)))
        b = int(255 * (1.0 - t * 0.85))
        g = int(220 * (1.0 - t * 0.35))
        r = int(80 + 175 * t)
        return (b, g, r)

    def _draw_depth_legend(self, bgr: np.ndarray) -> None:
        h, w = bgr.shape[:2]
        x0, y0 = 10, h - 36
        bar_w = 180
        cv2.putText(
            bgr, "深度", (x0, y0 - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA,
        )
        for i in range(bar_w):
            d = 0.20 + (0.40 * i / bar_w)
            c = self._depth_to_bgr(d)
            cv2.line(bgr, (x0 + i, y0), (x0 + i, y0 + 10), c, 1)
        cv2.putText(bgr, "近", (x0, y0 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 230, 255), 1, cv2.LINE_AA)
        cv2.putText(bgr, "远", (x0 + bar_w - 18, y0 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 180, 120), 1, cv2.LINE_AA)

    def _draw_hands_on_bgr(self, bgr: np.ndarray, hands: list[dict[str, Any]]) -> None:
        """骨架画进预览：连线按左右手，关节点按深度着色。"""
        h, w = bgr.shape[:2]
        for hand in hands:
            lm2d = hand.get("landmarks2d")
            depths_m = hand.get("depths_m")
            if not lm2d or len(lm2d) < 21:
                continue
            label = hand.get("label", "Right")
            side_color = (0, 200, 0) if label == "Left" else (0, 0, 200)
            pts = [(int(lm["x"] * w), int(lm["y"] * h)) for lm in lm2d]
            for i, j in HAND_CONNECTIONS:
                if i < len(pts) and j < len(pts):
                    cv2.line(bgr, pts[i], pts[j], side_color, 1, cv2.LINE_AA)
            for idx, pt in enumerate(pts):
                if depths_m and idx < len(depths_m):
                    pt_color = self._depth_to_bgr(depths_m[idx])
                    radius = 5 if idx in (4, 8, 12, 16, 20) else 4
                else:
                    pt_color = side_color
                    radius = 3
                cv2.circle(bgr, pt, radius, pt_color, -1, lineType=cv2.LINE_AA)
            proof = hand.get("depth_proof") or {}
            wrist_cm = proof.get("wrist_depth_cm")
            if wrist_cm is not None and pts:
                cv2.putText(
                    bgr,
                    f"{wrist_cm:.0f}cm",
                    (pts[0][0] + 6, pts[0][1] + 4),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
        self._draw_depth_legend(bgr)

    def _landmarks_3d(
        self, landmarks, depth_frame, img_w: int, img_h: int
    ) -> tuple[list[list[float]], list[float], dict[str, Any]] | None:
        wrist_u = int(np.clip(landmarks[0].x * img_w, 0, img_w - 1))
        wrist_v = int(np.clip(landmarks[0].y * img_h, 0, img_h - 1))
        wrist_depth = self._sample_depth_m(depth_frame, wrist_u, wrist_v) or 0.35

        points: list[np.ndarray] = []
        depths_m: list[float] = []
        for lm in landmarks:
            u = int(np.clip(lm.x * img_w, 0, img_w - 1))
            v = int(np.clip(lm.y * img_h, 0, img_h - 1))
            depth_m = self._sample_depth_m(depth_frame, u, v)
            if depth_m is None:
                depth_m = wrist_depth
            depths_m.append(float(depth_m))
            points.append(self._backproject(u, v, depth_m))

        pts = np.stack(points, axis=0)
        hand_pts = self._to_hand_frame(pts)
        depth_proof = {
            "source": "realsense_d405_depth",
            "wrist_depth_cm": round(depths_m[0] * 100, 1),
            "finger_spread_cm": round((max(depths_m) - min(depths_m)) * 100, 1),
            "thumb_tip_depth_cm": round(depths_m[4] * 100, 1),
            "index_tip_depth_cm": round(depths_m[8] * 100, 1),
            "middle_tip_depth_cm": round(depths_m[12] * 100, 1),
            "thumb_tip_3d": hand_pts[4].round(4).tolist(),
            "index_tip_3d": hand_pts[8].round(4).tolist(),
            "middle_tip_3d": hand_pts[12].round(4).tolist(),
        }
        return hand_pts.round(6).tolist(), depths_m, depth_proof

    def process_frame(self) -> dict[str, Any]:
        frames = self.pipeline.wait_for_frames(timeout_ms=5000)
        aligned = self.align.process(frames)
        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        if not depth_frame or not color_frame:
            return {"type": "frame", "fps": self._fps, "hands": []}

        color = np.asanyarray(color_frame.get_data())
        rgb = np.ascontiguousarray(cv2.cvtColor(color, cv2.COLOR_BGR2RGB))
        h, w = rgb.shape[:2]

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._video_ts_ms += int(1000 / COLOR_FPS)
        results = self.landmarker.detect_for_video(mp_image, self._video_ts_ms)
        hands_out: list[dict[str, Any]] = []

        if results.hand_landmarks and results.handedness:
            for hand_lms, handed in zip(results.hand_landmarks, results.handedness):
                packed = self._landmarks_3d(hand_lms, depth_frame, w, h)
                if packed is None:
                    continue
                lm3d, depths_m, depth_proof = packed
                cat = handed[0]
                label = cat.category_name
                lm2d_raw = [{"x": lm.x, "y": lm.y} for lm in hand_lms]
                lm2d = self._smooth_landmarks2d(label, lm2d_raw)
                hands_out.append(
                    {
                        "label": label,
                        "score": round(float(cat.score), 4),
                        "landmarks": lm3d,
                        "landmarks2d": lm2d,
                        "depth_proof": depth_proof,
                        "depths_m": depths_m,
                    }
                )

        now_draw = time.time()
        if hands_out:
            self._last_hands_draw = hands_out
            self._last_hands_draw_t = now_draw
        elif now_draw - self._last_hands_draw_t > HANDS_HOLD_S:
            self._last_hands_draw = []
            self._smooth_2d.clear()

        hands_for_preview = hands_out if hands_out else self._last_hands_draw

        self._frame_count += 1
        now = time.time()
        if now - self._last_fps_time >= 1.0:
            self._fps = round(self._frame_count / (now - self._last_fps_time), 1)
            self._frame_count = 0
            self._last_fps_time = now

        payload: dict[str, Any] = {
            "type": "frame",
            "fps": self._fps,
            "hands": [
                {k: v for k, v in hand.items() if k != "depths_m"}
                for hand in hands_out
            ],
        }

        preview_bgr = color.copy()
        if hands_for_preview:
            self._draw_hands_on_bgr(preview_bgr, hands_for_preview)
        preview = cv2.resize(preview_bgr, (PREVIEW_W, PREVIEW_H))
        ok, buf = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            payload["preview"] = base64.b64encode(buf.tobytes()).decode("ascii")

        return payload


clients: set[Any] = set()


async def register_client(websocket) -> None:
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)


async def main() -> None:
    print("=" * 60)
    print("D405 3D 手部跟踪服务")
    print(f"WebSocket: ws://{WS_HOST}:{WS_PORT}")
    print("请在浏览器打开 7.follow-me-3d 页面")
    print("按 Ctrl+C 退出")
    print("=" * 60)

    async with serve(register_client, WS_HOST, WS_PORT):
        tracker = RealSenseHandTracker()
        print(f"[tracker] RealSense D405 已启动 {COLOR_W}x{COLOR_H}@{COLOR_FPS}")
        try:
            while True:
                if not clients:
                    await asyncio.sleep(0.05)
                    continue
                payload = tracker.process_frame()
                msg = json.dumps(payload)
                dead = []
                for ws in list(clients):
                    try:
                        await ws.send(msg)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    clients.discard(ws)
                await asyncio.sleep(0)
        finally:
            tracker.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已停止")
