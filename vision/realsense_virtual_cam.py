"""
RealSense D405 彩色流 -> 虚拟摄像头（供浏览器 / 石头剪刀布游戏使用）

D405 的 Color 流只能通过 RealSense SDK 获取，浏览器 getUserMedia 只能看到 Depth UVC 设备。
本脚本用 pyrealsense2 读取 Color，经 pyvirtualcam 输出为系统虚拟摄像头。

【前置条件】
  1. 已安装 Intel RealSense SDK 2.0（含 D405 驱动）
  2. 已安装 OBS Studio（26+），用于提供 Windows 虚拟摄像头后端
  3. 关闭 RealSense Viewer / Depth Quality Tool（避免占用相机）

【安装依赖】（新建环境或现有 Python 3.10+ 均可）
  pip install -r realsense_virtual_cam_requirements.txt

【运行】
  python realsense_virtual_cam.py

【在游戏中】
  摄像头下拉框选择「OBS Virtual Camera」（或脚本打印的虚拟设备名），
  不要选 Intel RealSense Depth Camera 405 Depth。
"""

from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np

try:
    import pyrealsense2 as rs
except ImportError:
    print("缺少 pyrealsense2，请执行：")
    print("  pip install -r realsense_virtual_cam_requirements.txt")
    sys.exit(1)

try:
    import pyvirtualcam
except ImportError:
    print("缺少 pyvirtualcam，请执行：")
    print("  pip install -r realsense_virtual_cam_requirements.txt")
    sys.exit(1)


# D405 常用配置（640x480 对 USB2/虚拟摄像头都较稳）
DEFAULT_PROFILES = [
    (640, 480, 30),
    (848, 480, 30),
    (640, 480, 15),
    (424, 240, 30),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RealSense D405 Color -> Virtual Camera")
    parser.add_argument("--width", type=int, default=0, help="强制宽度，0 表示自动尝试")
    parser.add_argument("--height", type=int, default=0, help="强制高度，0 表示自动尝试")
    parser.add_argument("--fps", type=int, default=0, help="强制帧率，0 表示自动尝试")
    parser.add_argument("--warmup", type=int, default=30, help="启动后丢弃的预热帧数")
    parser.add_argument(
        "--no-depth",
        action="store_true",
        help="不启用 depth 流（部分固件需同时开 depth 才有 color，默认会开 depth）",
    )
    return parser.parse_args()


def build_profiles(args: argparse.Namespace) -> list[tuple[int, int, int]]:
    if args.width and args.height and args.fps:
        return [(args.width, args.height, args.fps)]
    if args.width or args.height or args.fps:
        print("请同时指定 --width --height --fps，或都不指定使用自动配置")
        sys.exit(1)
    return DEFAULT_PROFILES


def start_realsense(
    profiles: list[tuple[int, int, int]],
    color_only: bool,
) -> tuple[rs.pipeline, tuple[int, int, int]]:
    last_error: Exception | None = None

    for width, height, fps in profiles:
        pipeline = rs.pipeline()
        config = rs.config()
        try:
            if not color_only:
                config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
            config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
            pipeline.start(config)
            print(f"RealSense 已启动 Color 流: {width}x{height} @ {fps}fps")
            return pipeline, (width, height, fps)
        except Exception as exc:
            last_error = exc
            try:
                pipeline.stop()
            except Exception:
                pass
            print(f"  尝试 {width}x{height}@{fps} 失败: {exc}")

    print("\n无法启动 RealSense Color 流。请检查：")
    print("  · D405 是否插好、是否 USB 3.0 口")
    print("  · RealSense Viewer 是否已关闭")
    print("  · Intel RealSense SDK / 驱动是否已安装")
    if last_error:
        print(f"  · 最后一次错误: {last_error}")
    sys.exit(1)


def warmup(pipeline: rs.pipeline, frames: int) -> None:
    if frames <= 0:
        return
    print(f"预热 {frames} 帧...")
    for _ in range(frames):
        pipeline.wait_for_frames()


def main() -> None:
    args = parse_args()
    profiles = build_profiles(args)
    color_only = args.no_depth

    print("=" * 60)
    print("RealSense D405 彩色 -> 虚拟摄像头")
    print("=" * 60)

    pipeline, (width, height, fps) = start_realsense(profiles, color_only)
    warmup(pipeline, args.warmup)

    try:
        with pyvirtualcam.Camera(width=width, height=height, fps=fps, print_fps=True) as cam:
            print()
            print(f"虚拟摄像头已就绪: {cam.device}")
            print()
            print("下一步：")
            print("  1. 保持本窗口运行")
            print("  2. 打开 http://localhost:8899/6.gameplay/")
            print("  3. 摄像头下拉框选择「OBS Virtual Camera」或上面显示的设备名")
            print("  4. 不要选 Intel RealSense Depth Camera 405 Depth")
            print()
            print("按 Ctrl+C 退出")
            print("-" * 60)

            while True:
                frames = pipeline.wait_for_frames(timeout_ms=5000)
                color_frame = frames.get_color_frame()
                if not color_frame:
                    continue

                bgr = np.asanyarray(color_frame.get_data())
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                cam.send(rgb)
                cam.sleep_until_next_frame()

    except KeyboardInterrupt:
        print("\n已停止")
    except RuntimeError as exc:
        msg = str(exc)
        print(f"\n虚拟摄像头错误: {msg}")
        if "obs" in msg.lower() or "OBS" in msg:
            print("\nWindows 需要 OBS Studio 提供虚拟摄像头：")
            print("  1. 安装 OBS Studio 26 或更高版本")
            print("  2. 打开 OBS -> 工具 -> 启动虚拟摄像头（Start Virtual Camera）")
            print("  3. 再重新运行本脚本")
        sys.exit(1)
    finally:
        pipeline.stop()
        print("RealSense 已释放")


if __name__ == "__main__":
    main()
