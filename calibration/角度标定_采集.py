"""
角度标定_采集.py

【测试目的】
  从原始值 255 开始每隔 15 递减到 0，控制灵巧手单关节运动，
  同时记录 WitMotion 传感器读数，输出 CSV 供线性拟合使用。

【前置条件】
  · 已激活 linkerbot 虚拟环境
  · 在本目录执行：cd testing/calibration
  · PCAN 已连接，灵巧手已上电；HAND_SIDE 与实物一致
  · WitMotion 固定在被测手指上，上位机可正常读数
  · 关闭 PCAN-View 等占用 PCAN 通道的程序

【操作步骤】
  方式 A - 手动输入（默认）：
    1. 修改顶部配置区
    2. RECORD_MODE = "manual"
    3. 执行：python 角度标定_采集.py

  方式 B - WitMotion 上位机「开始记录」+ 自动合并：
    1. RECORD_MODE = "witmotion_record"
    2. 先在 WitMotion 上位机点「开始记录」
    3. 执行：python 角度标定_采集.py
    4. 上位机点「结束记录」，找到 Data.tsv
    5. 执行：python 角度标定_合并witmotion记录.py
    6. 执行：python 角度标定_拟合.py

【预期结果】
  · 手指按 255→240→…→0 依次运动并停稳
  · 生成 calibration_data.csv，含 raw_value / sdk_value / witmotion_x

【实际结果】
  （测试后在此填写）

【说明】
  · SDK 角度 0~100 对应底层原始值 0~255（见 angle.md）
  · 关节顺序：[thumb_flex, thumb_abd, index, middle, ring, pinky]
  · WITMOTION_AXIS：选 WitMotion 软件里变化最大的轴（常见 roll / pitch / yaw）
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import Literal

from linkerbot import L6, O6
from linkerbot.exceptions import TimeoutError as LinkerTimeoutError

_DIR = Path(__file__).resolve().parent
_DATA_DIR = _DIR / "data"
_DATA_DIR.mkdir(exist_ok=True)
_POSES_DIR = _DIR.parent / "poses"
if str(_POSES_DIR) not in sys.path:
    sys.path.insert(0, str(_POSES_DIR))
from pose_common import exit_if_hand_offline

AxisName = Literal["roll", "pitch", "yaw"]

# ========== 顶部配置区 ==========
HAND_SIDE = "left"              # "left" / "right"
HAND_MODEL = "L6"               # "L6" 或 "O6"，与实物一致
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"

JOINT_INDEX = 2                 # 0~5，默认 2=食指(index)
RAW_STEP = 15                   # 原始值步长
SETTLE_TIME_SEC = 3.0           # 每个点停稳等待时间
MOVE_SPEED = 20                 # 运动速度，保持低速安全
OTHER_JOINT_OPEN = 100.0        # 非被测关节保持全张开（0=蜷缩，100=张开）

# WitMotion 配置
# RECORD_MODE:
#   "manual"           -> 每个点手动输入角度（默认）
#   "witmotion_record" -> 配合上位机「开始记录」，之后用 角度标定_合并witmotion记录.py
#   "serial"           -> Type-C 有线 + COM 口自动读取
RECORD_MODE = "witmotion_record"
WITMOTION_PORT = ""             # serial 模式填 "COM3"
WITMOTION_BAUD = 115200         # 蓝牙固定 115200；Type-C 常见 115200
WITMOTION_AXIS: AxisName = "roll"  # 对应上位机「角度 X」
WITMOTION_SAMPLES = 20          # serial 模式下取平均的样本数

OUTPUT_CSV = "data/calibration_data.csv"
MARKERS_CSV = "data/calibration_markers.csv" 
READ_TIMEOUT_MS = 3000
# ==================================

JOINT_NAMES = [
    "thumb_flex",
    "thumb_abd",
    "index",
    "middle",
    "ring",
    "pinky",
]

RAW_VALUES = list(range(255, -1, -RAW_STEP))


def _create_hand():
    if HAND_MODEL == "L6":
        return L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE)
    if HAND_MODEL == "O6":
        return O6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE)
    raise ValueError(f"HAND_MODEL 必须是 L6 或 O6，当前为 {HAND_MODEL!r}")


def _build_target_angles(joint_index: int, sdk_value: float) -> list[float]:
    angles = [OTHER_JOINT_OPEN] * 6
    angles[joint_index] = sdk_value
    return angles


def _prompt_manual_reading(raw_value: int, sdk_value: float) -> float:
    while True:
        text = input(
            f"[raw={raw_value:3d}, sdk={sdk_value:6.2f}] "
            f"请输入 WitMotion {WITMOTION_AXIS} 读数（度），q 退出: "
        ).strip()
        if text.lower() == "q":
            raise KeyboardInterrupt
        try:
            return float(text)
        except ValueError:
            print("输入无效，请重新输入数字。")


def _read_witmotion_value(witmotion, raw_value: int, sdk_value: float) -> float | None:
    if RECORD_MODE == "witmotion_record":
        return None

    if witmotion is None:
        return _prompt_manual_reading(raw_value, sdk_value)

    sample = witmotion.read_average(
        samples=WITMOTION_SAMPLES,
        sample_interval_sec=0.05,
        timeout_sec=5.0,
    )
    if sample is None:
        print("WitMotion 自动读取失败，改为手动输入。")
        return _prompt_manual_reading(raw_value, sdk_value)

    value = sample.get_axis(WITMOTION_AXIS)
    print(
        f"  WitMotion roll={sample.roll:7.2f}, pitch={sample.pitch:7.2f}, "
        f"yaw={sample.yaw:7.2f} -> 使用 {WITMOTION_AXIS}={value:7.2f}"
    )
    return value


def main() -> int:
    output_path = _DIR / OUTPUT_CSV
    markers_path = _DIR / MARKERS_CSV
    witmotion = None

    if RECORD_MODE == "serial" or WITMOTION_PORT:
        from witmotion_serial import WitMotionReader

        if not WITMOTION_PORT:
            print("❌ serial 模式需要设置 WITMOTION_PORT，例如 COM3")
            return 1
        witmotion = WitMotionReader(port=WITMOTION_PORT, baudrate=WITMOTION_BAUD)

    mode_desc = {
        "manual": "手动输入",
        "witmotion_record": "上位机录制 + 事后合并",
        "serial": f"串口自动({WITMOTION_PORT})",
    }.get(RECORD_MODE, RECORD_MODE)

    print("=== 角度标定：数据采集 ===")
    print(f"HAND_MODEL = {HAND_MODEL}, HAND_SIDE = {HAND_SIDE}")
    print(f"目标关节 = {JOINT_NAMES[JOINT_INDEX]} (index={JOINT_INDEX})")
    print(f"采样点 raw = {RAW_VALUES}")
    print(f"RECORD_MODE = {RECORD_MODE} ({mode_desc})")
    if RECORD_MODE == "witmotion_record":
        print(f"标记文件 = {markers_path.resolve()}")
        print("\n操作顺序：")
        print("  1. 在 WitMotion 上位机点击「开始记录」")
        print("  2. 立刻回到此窗口按回车（尽量在 1~2 秒内）")
        input("按回车开始控制灵巧手采集...")
        record_start_unix = time.time()
    else:
        record_start_unix = None
        print(f"输出文件 = {output_path.resolve()}")
    print()

    rows: list[dict[str, float | int | str]] = []

    try:
        hand_ctx = _create_hand()
    except Exception as exc:
        if "PcanCanInitializationError" in type(exc).__name__ or "PCAN" in str(exc):
            print("\n❌ PCAN 初始化失败，无法连接灵巧手。")
            print("请按顺序检查：")
            print("  1. PCAN 适配器是否插好 USB")
            print("  2. 是否已安装 PEAK 驱动：https://peak-system.com.cn/driver/")
            print("  3. 设备管理器里是否能看到 PCAN 设备")
            print("  4. 是否关闭了 PCAN-View 等占用通道的程序")
            print("  5. INTERFACE 是否为 PCAN_USBBUS1（第二个设备试 PCAN_USBBUS2）")
            print("  6. 灵巧手是否已上电")
            return 1
        raise

    with hand_ctx as hand:
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)

        exit_if_hand_offline(hand, HAND_SIDE)

        hand.speed.set_speeds([MOVE_SPEED] * 6)
        if HAND_MODEL == "O6":
            hand.acceleration.set_accelerations([MOVE_SPEED] * 6)

        print("\n先将非被测手指移动到全张开...")
        hand.angle.set_angles([OTHER_JOINT_OPEN] * 6)
        time.sleep(SETTLE_TIME_SEC)

        for raw_value in RAW_VALUES:
            sdk_value = raw_value / 255.0 * 100.0
            target = _build_target_angles(JOINT_INDEX, sdk_value)

            print(f"\n--- raw={raw_value}, sdk={sdk_value:.2f} ---")
            hand.angle.set_angles(target)
            time.sleep(SETTLE_TIME_SEC)

            try:
                feedback = hand.angle.get_blocking(timeout_ms=READ_TIMEOUT_MS)
                feedback_value = feedback.angles.to_list()[JOINT_INDEX]
            except LinkerTimeoutError:
                print("读角超时，feedback_sdk_value 记为 NaN")
                feedback_value = float("nan")

            witmotion_value = _read_witmotion_value(witmotion, raw_value, sdk_value)
            sample_unix = time.time()

            if RECORD_MODE == "witmotion_record":
                marker_row = {
                    "raw_value": raw_value,
                    "sdk_value": round(sdk_value, 4),
                    "feedback_sdk_value": round(feedback_value, 4) if feedback_value == feedback_value else "",
                    "witmotion_axis": WITMOTION_AXIS,
                    "joint": JOINT_NAMES[JOINT_INDEX],
                    "hand_model": HAND_MODEL,
                    "hand_side": HAND_SIDE,
                    "record_start_unix": round(record_start_unix, 3),
                    "sample_unix": round(sample_unix, 3),
                }
                rows.append(marker_row)
                print(
                    f"已标记 raw={raw_value}, sdk={sdk_value:.2f}, "
                    f"feedback={feedback_value:.2f}, t={sample_unix - record_start_unix:.1f}s"
                )
                continue

            row = {
                "motor_raw": raw_value,
                "angle_x": round(witmotion_value, 4),
            }
            rows.append(row)
            print(
                f"已记录 motor_raw={raw_value}, sdk={sdk_value:.2f}, "
                f"feedback={feedback_value:.2f}, angle_x={witmotion_value:.2f}"
            )

    if RECORD_MODE == "witmotion_record":
        marker_fields = [
            "raw_value",
            "sdk_value",
            "feedback_sdk_value",
            "witmotion_axis",
            "joint",
            "hand_model",
            "hand_side",
            "record_start_unix",
            "sample_unix",
        ]
        with markers_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=marker_fields)
            writer.writeheader()
            writer.writerows(rows)

        if witmotion is not None:
            witmotion.close()

        print(f"\n✅ 时间标记已保存到 {markers_path.resolve()}")
        print("请在 WitMotion 上位机点击「结束记录」，找到 Data.tsv")
        print("然后执行：python 角度标定_合并witmotion记录.py")
        return 0

    fieldnames = ["motor_raw", "angle_x"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if witmotion is not None:
        witmotion.close()

    print(f"\n✅ 采集完成，共 {len(rows)} 行，已保存到 {output_path.resolve()}")
    print("下一步：python 角度标定_拟合.py")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n采集已中断。")
        sys.exit(1)
