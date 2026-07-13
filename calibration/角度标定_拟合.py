"""
角度标定_拟合.py

【测试目的】
  读取 calibration_data.csv，对 motor_raw 与 angle_x 做线性回归，
  输出线性函数、R²、RMSE，用于判断线性度是否接近 1。

【前置条件】
  · 已运行 角度标定_采集.py 并生成 CSV
  · 环境中已有 numpy / scipy（linkerbot 依赖已包含）

【操作步骤】
  1. 确认 CSV_FILE 路径正确（默认 calibration_data.csv）
  2. 执行：python 角度标定_拟合.py

【预期结果】
  · 打印 angle_x = m * motor_raw + b
  · R² 接近 1 表示线性度好，可用于映射代码

【实际结果】
  （测试后在此填写）

【说明】
  R²（决定系数）= 1 - SS_res / SS_tot
  · SS_res = Σ(y - ŷ)²   预测误差平方和
  · SS_tot = Σ(y - ȳ)²   总方差
  · R² 越接近 1，说明控制值与真实角度越接近直线关系
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from scipy import stats

_DIR = Path(__file__).resolve().parent

# ========== 顶部配置区 ==========
CSV_FILE = "data/calibration_data.csv"
# ==================================


def compute_r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return 1.0 - ss_res / ss_tot


def _read_row(row: dict[str, str]) -> tuple[float, float]:
    if "motor_raw" in row and "angle_x" in row:
        return float(row["motor_raw"]), float(row["angle_x"])
    return float(row["raw_value"]), float(row["witmotion_x"])


def main() -> int:
    path = _DIR / CSV_FILE
    if not path.exists():
        print(f"❌ 找不到 CSV 文件: {path.resolve()}")
        print("请先运行: python 角度标定_采集.py")
        return 1

    raw_values: list[float] = []
    witmotion_values: list[float] = []

    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        for row in reader:
            motor_raw, angle_x = _read_row(row)
            raw_values.append(motor_raw)
            witmotion_values.append(angle_x)

    if len(raw_values) < 2:
        print("❌ 至少需要 2 个采样点才能拟合。")
        return 1

    x = np.array(raw_values, dtype=float)
    y = np.array(witmotion_values, dtype=float)

    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    y_pred = slope * x + intercept
    r_squared = compute_r_squared(y, y_pred)
    rmse = float(np.sqrt(np.mean((y - y_pred) ** 2)))
    max_abs_error = float(np.max(np.abs(y - y_pred)))

    print("=== 角度标定：线性拟合 ===")
    print(f"输入文件: {path.resolve()}")
    print(f"样本数: {len(x)}")
    print()
    print("【线性函数】")
    print(f"  angle_x = {slope:.6f} * motor_raw + ({intercept:.6f})")
    if slope != 0:
        print(f"  motor_raw = (angle_x - ({intercept:.6f})) / {slope:.6f}")
    print()
    print("【拟合质量】")
    print(f"  Pearson r     = {r_value:.6f}")
    print(f"  R²            = {r_squared:.6f}")
    print(f"  p-value       = {p_value:.6g}")
    print(f"  斜率标准误差  = {std_err:.6f}")
    print(f"  RMSE          = {rmse:.6f} °")
    print(f"  最大绝对误差  = {max_abs_error:.6f} °")
    print()
    if r_squared >= 0.99:
        print("线性度评价: 优秀 (R² >= 0.99)")
    elif r_squared >= 0.95:
        print("线性度评价: 良好 (0.95 <= R² < 0.99)")
    else:
        print("线性度评价: 较弱 (R² < 0.95)，建议检查传感器安装或采样过程。")

    print()
    print("【逐点误差表】")
    print("  motor_raw   实测(angle_x)   预测值      误差")
    for raw, actual, predicted in zip(x, y, y_pred, strict=True):
        error = actual - predicted
        print(f"  {raw:8.0f}   {actual:14.4f}   {predicted:10.4f}   {error:8.4f}")

    print()
    print("【映射代码示例】")
    print("def motor_raw_to_angle_x(motor_raw: float) -> float:")
    print(f"    return {slope:.6f} * motor_raw + ({intercept:.6f})")
    print()
    print("def angle_x_to_motor_raw(angle_x: float) -> float:")
    if slope != 0:
        print(f"    return (angle_x - ({intercept:.6f})) / {slope:.6f}")
    else:
        print("    raise ValueError('斜率为 0，无法反算 motor_raw')")

    print("\n✅ 拟合完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
