"""
角度标定_合并指根指尖.py

合并指根与指尖数据，并计算第二关节角度：
  angle_joint2 = angle_x_tip - angle_x_root

拟合应使用：指根角度 vs 第二关节角度（而非指尖累积角度）。
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from scipy import stats

_DIR = Path(__file__).resolve().parent
_DATA_DIR = _DIR / "data"

FINGERS = {
    "1a": "拇指弯曲 (thumb_flex)",
    "1b": "拇指侧摆 (thumb_abd)",
    "2": "食指 (index)",
    "3": "中指 (middle)",
    "4": "无名指 (ring)",
    "5": "小指 (pinky)",
}


def _load_csv(path: Path) -> dict[int, float]:
    data: dict[int, float] = {}
    with path.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            raw = row.get("motor_raw", "").strip()
            angle = row.get("angle_x", "").strip()
            if not raw or not angle:
                continue
            data[int(float(raw))] = float(angle)
    return data


def _average_tip(finger_id: str) -> dict[int, float]:
    files = sorted(_DATA_DIR.glob(f"calibration_data_tip_{finger_id}.*.csv"))
    if not files:
        raise FileNotFoundError(f"找不到指尖数据: tip_{finger_id}.*.csv")

    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for path in files:
        for raw, angle in _load_csv(path).items():
            sums[raw] = sums.get(raw, 0.0) + angle
            counts[raw] = counts.get(raw, 0) + 1

    return {raw: sums[raw] / counts[raw] for raw in sums}


def _fit_linear(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    slope, intercept, r, _, _ = stats.linregress(x, y)
    return slope, intercept, r**2


def _fit_quadratic(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    coeffs = np.polyfit(x, y, 2)
    y_pred = np.polyval(coeffs, x)
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    return coeffs, r2


def merge_and_analyze() -> None:
    all_rows: list[dict[str, str | float | int]] = []
    print("=== 指根-第二关节 合并与分析 ===\n")
    print("说明: angle_joint2 = angle_x_tip - angle_x_root (第二关节弯曲角)\n")

    for finger_id, finger_name in FINGERS.items():
        root_path = _DATA_DIR / f"calibration_data_{finger_id}.csv"
        if not root_path.exists():
            print(f"⚠ 跳过 {finger_id}：找不到 {root_path.name}")
            continue

        root = _load_csv(root_path)
        tip = _average_tip(finger_id)
        tip_files = sorted(_DATA_DIR.glob(f"calibration_data_tip_{finger_id}.*.csv"))

        motor_raws = sorted(set(root) & set(tip))
        if len(motor_raws) < 2:
            print(f"⚠ 跳过 {finger_id}：指根与指尖 motor_raw 交集不足")
            continue

        merged_rows: list[dict[str, str | float | int]] = []
        for raw in motor_raws:
            joint2 = tip[raw] - root[raw]
            row = {
                "finger_id": finger_id,
                "finger": finger_name,
                "motor_raw": raw,
                "angle_x_root": round(root[raw], 4),
                "angle_x_tip": round(tip[raw], 4),
                "angle_joint2": round(joint2, 4),
            }
            merged_rows.append(row)
            all_rows.append(row)

        merged_path = _DATA_DIR / f"merged_{finger_id}.csv"
        fieldnames = [
            "finger_id",
            "finger",
            "motor_raw",
            "angle_x_root",
            "angle_x_tip",
            "angle_joint2",
        ]
        with merged_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(merged_rows)

        x_motor = np.array(motor_raws, dtype=float)
        y_root = np.array([root[r] for r in motor_raws], dtype=float)
        y_joint2 = np.array([tip[r] - root[r] for r in motor_raws], dtype=float)

        _, _, r2_motor_root = _fit_linear(x_motor, y_root)
        _, _, r2_motor_joint2 = _fit_linear(x_motor, y_joint2)
        slope_rj, intercept_rj, r2_root_joint2_lin = _fit_linear(y_root, y_joint2)
        quad_coeffs, r2_root_joint2_quad = _fit_quadratic(y_root, y_joint2)
        rmse_lin = float(
            np.sqrt(np.mean((y_joint2 - (slope_rj * y_root + intercept_rj)) ** 2))
        )

        print(f"【{finger_id}】{finger_name}")
        print(f"  指尖数据来源: {[p.name for p in tip_files]}")
        print(f"  合并文件: {merged_path.name}  ({len(merged_rows)} 点)")
        print(f"  motor_raw -> 指根 angle_x:      R^2 = {r2_motor_root:.4f}")
        print(f"  motor_raw -> 第二关节 angle:    R^2 = {r2_motor_joint2:.4f}")
        print(
            f"  指根 -> 第二关节 (线性):  angle_joint2 = {slope_rj:.4f} * angle_x_root + ({intercept_rj:.4f})"
        )
        print(f"                            R^2 = {r2_root_joint2_lin:.4f}  RMSE = {rmse_lin:.2f} deg")
        print(
            f"  指根 -> 第二关节 (二次):  angle_joint2 = {quad_coeffs[0]:.6f}*root^2 + "
            f"{quad_coeffs[1]:.4f}*root + ({quad_coeffs[2]:.4f})"
        )
        print(f"                            R^2 = {r2_root_joint2_quad:.4f}")

        if r2_root_joint2_quad - r2_root_joint2_lin > 0.01:
            print("  结论: 指根-第二关节关系有明显非线性，二次拟合更好")
        elif r2_root_joint2_lin >= 0.99:
            print("  结论: 指根-第二关节近似线性")
        else:
            print("  结论: 指根-第二关节非线性更明显，符合老师预期")
        print()

    if not all_rows:
        print("❌ 没有可合并的数据")
        return

    all_path = _DATA_DIR / "merged_all.csv"
    fieldnames = [
        "finger_id",
        "finger",
        "motor_raw",
        "angle_x_root",
        "angle_x_tip",
        "angle_joint2",
    ]
    with all_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"[OK] 全部合并完成: {all_path.resolve()}")
    print(f"   各指单独文件: merged_1a.csv ~ merged_5.csv")


if __name__ == "__main__":
    merge_and_analyze()
