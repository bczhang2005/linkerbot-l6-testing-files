"""
角度标定_合并witmotion记录.py

【测试目的】
  把 WitMotion 上位机「开始记录」导出的 Data.tsv，与采集脚本生成的时间标记
  calibration_markers.csv 合并，自动得到 calibration_data.csv。

【前置条件】
  · 已用 RECORD_MODE = "witmotion_record" 跑完 角度标定_采集.py
  · WitMotion 上位机在采集前点了「开始记录」，采集结束后点「结束记录」
  · 找到上位机保存的记录文件（常见名 Data.tsv，在 WitMotion 安装目录或 Record 文件夹）

【操作步骤】
  1. 修改 WITMOTION_RECORD_FILE 为实际路径
  2. 执行：python 角度标定_合并witmotion记录.py
  3. 再执行：python 角度标定_拟合.py

【说明】
  · 合并原理：采集脚本在每个采样点停稳时写入 unix 时间戳；
    与 WitMotion 记录开始时间的差值，用来在记录文件里取对应时刻的角度 X 平均值。
  · 若合并失败，检查 WitMotion 是否在整个采集过程中一直在录制。
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

from witmotion_export import average_near_time, load_witmotion_export

_DIR = Path(__file__).resolve().parent

# ========== 顶部配置区 ==========
MARKERS_FILE = "data/calibration_markers.csv"
WITMOTION_RECORD_FILE = r"WitMotion/Record/<日期>/<时间>/data_0.csv"   # 改成 WitMotion 记录文件的实际路径
OUTPUT_CSV = "data/calibration_data.csv"
WITMOTION_AXIS = "roll"              # 对应上位机「角度 X」
MERGE_WINDOW_SEC = 1.0               # 在标记时间前后各取多少秒做平均
WITMOTION_TIME_OFFSET_SEC = 0.0        # 若合并结果整体偏早/偏晚，可微调（秒）
# ==================================


def main() -> int:
    markers_path = _DIR / MARKERS_FILE
    record_path = Path(WITMOTION_RECORD_FILE)
    output_path = _DIR / OUTPUT_CSV

    if not markers_path.exists():
        print(f"❌ 找不到 {markers_path.resolve()}")
        print("请先以 RECORD_MODE = 'witmotion_record' 运行 角度标定_采集.py")
        return 1
    if not record_path.exists():
        print(f"❌ 找不到 WitMotion 记录文件: {record_path.resolve()}")
        print("请在上位机里找到 Data.tsv 或导出 txt，并修改 WITMOTION_RECORD_FILE")
        return 1

    with markers_path.open(newline="", encoding="utf-8-sig") as file:
        markers = list(csv.DictReader(file))

    if not markers:
        print("❌ 标记文件为空")
        return 1

    record_start_unix = float(markers[0]["record_start_unix"])
    series = load_witmotion_export(record_path, axis=WITMOTION_AXIS)

    print("=== 合并 WitMotion 记录 ===")
    print(f"标记文件: {markers_path.resolve()}")
    print(f"WitMotion 记录: {record_path.resolve()}")
    print(f"记录开始时间: {datetime.fromtimestamp(record_start_unix)}")
    print(f"使用角度列: {series.axis_column}")
    print(f"使用时间列: {series.time_column}")
    print(f"WitMotion 数据行数: {len(series.values)}")
    print()

    rows: list[dict[str, str | float | int]] = []
    failed = 0

    for marker in markers:
        sample_unix = float(marker["sample_unix"])
        relative_sec = sample_unix - record_start_unix + WITMOTION_TIME_OFFSET_SEC
        witmotion_value = average_near_time(series, relative_sec, MERGE_WINDOW_SEC)

        if witmotion_value is None:
            failed += 1
            print(
                f"⚠ raw={marker['raw_value']} 在 t={relative_sec:.1f}s 附近未找到 WitMotion 数据"
            )
            witmotion_value = float("nan")

        row = {
            "motor_raw": int(marker["raw_value"]),
            "angle_x": round(witmotion_value, 4) if witmotion_value == witmotion_value else "",
        }
        rows.append(row)
        if witmotion_value == witmotion_value:
            print(
                f"motor_raw={row['motor_raw']:3d}  t={relative_sec:6.1f}s  "
                f"angle_x={witmotion_value:8.3f}"
            )

    fieldnames = ["motor_raw", "angle_x"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if failed:
        print(f"\n⚠ 有 {failed} 个点未能自动匹配，请检查录制是否覆盖整个采集过程。")
        return 1

    print(f"\n✅ 已生成 {output_path.resolve()}")
    print("下一步：python 角度标定_拟合.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
