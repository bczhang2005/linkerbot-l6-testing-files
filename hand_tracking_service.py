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
PREVIEW_EVERY_N = 2
DEPTH_PATCH = 3
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

    def _landmarks_3d(
        self, landmarks, depth_frame, img_w: int, img_h: int
    ) -> list[list[float]] | None:
        points: list[np.ndarray] = []
        for lm in landmarks:
            u = int(np.clip(lm.x * img_w, 0, img_w - 1))
            v = int(np.clip(lm.y * img_h, 0, img_h - 1))
            depth_m = self._sample_depth_m(depth_frame, u, v)
            if depth_m is None:
                depth_m = 0.35
            points.append(self._backproject(u, v, depth_m))

        pts = np.stack(points, axis=0)
        hand_pts = self._to_hand_frame(pts)
        return hand_pts.round(6).tolist()

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
                lm3d = self._landmarks_3d(hand_lms, depth_frame, w, h)
                if lm3d is None:
                    continue
                cat = handed[0]
                hands_out.append(
                    {
                        "label": cat.category_name,
                        "score": round(float(cat.score), 4),
                        "landmarks": lm3d,
                    }
                )

        self._frame_count += 1
        now = time.time()
        if now - self._last_fps_time >= 1.0:
            self._fps = round(self._frame_count / (now - self._last_fps_time), 1)
            self._frame_count = 0
            self._last_fps_time = now

        payload: dict[str, Any] = {
            "type": "frame",
            "fps": self._fps,
            "hands": hands_out,
        }

        if self._frame_count % PREVIEW_EVERY_N == 0:
            preview = cv2.resize(color, (320, 240))
            ok, buf = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
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
