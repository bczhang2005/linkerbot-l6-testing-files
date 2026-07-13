"""Plot root vs second-joint angle calibration results."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

_DIR = Path(__file__).resolve().parent
_DATA_DIR = _DIR / "data"
_OUTPUT_DIR = _DATA_DIR / "plots"
_OUTPUT_DIR.mkdir(exist_ok=True)

FINGERS = ["1a", "1b", "2", "3", "4", "5"]
FINGER_LABELS = {
    "1a": "Thumb flex",
    "1b": "Thumb abd",
    "2": "Index",
    "3": "Middle",
    "4": "Ring",
    "5": "Pinky",
}


def _load_merged(finger_id: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    path = _DATA_DIR / f"merged_{finger_id}.csv"
    motor, root, tip, joint2 = [], [], [], []
    with path.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            motor.append(float(row["motor_raw"]))
            root.append(float(row["angle_x_root"]))
            tip.append(float(row["angle_x_tip"]))
            if "angle_joint2" in row:
                joint2.append(float(row["angle_joint2"]))
            else:
                joint2.append(float(row["angle_x_tip"]) - float(row["angle_x_root"]))
    return (
        np.array(motor),
        np.array(root),
        np.array(tip),
        np.array(joint2),
    )


def plot_root_vs_joint2() -> Path:
    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    fig.suptitle("Root angle vs 2nd-joint angle (tip - root)", fontsize=14)

    for ax, finger_id in zip(axes.flat, FINGERS):
        _, root, _, joint2 = _load_merged(finger_id)
        order = np.argsort(root)
        root_s = root[order]
        joint2_s = joint2[order]

        slope, intercept, r, _, _ = stats.linregress(root_s, joint2_s)
        quad = np.polyfit(root_s, joint2_s, 2)
        x_line = np.linspace(root_s.min(), root_s.max(), 200)
        y_lin = slope * x_line + intercept
        y_quad = np.polyval(quad, x_line)

        ax.scatter(root_s, joint2_s, c="#2563eb", s=40, zorder=3, label="data")
        ax.plot(x_line, y_lin, "r--", lw=1.8, label=f"linear R^2={r**2:.4f}")
        r2_quad = 1 - np.sum((joint2_s - np.polyval(quad, root_s)) ** 2) / np.sum(
            (joint2_s - joint2_s.mean()) ** 2
        )
        ax.plot(x_line, y_quad, "g-", lw=1.5, label=f"quad R^2={r2_quad:.4f}")

        ax.set_title(FINGER_LABELS[finger_id])
        ax.set_xlabel("angle_x_root (1st joint, deg)")
        ax.set_ylabel("angle_joint2 = tip - root (deg)")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)

    plt.tight_layout()
    out = _OUTPUT_DIR / "root_vs_joint2.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_decomposition() -> Path:
    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    fig.suptitle("Angle decomposition: root + joint2 = tip (cumulative)", fontsize=14)

    for ax, finger_id in zip(axes.flat, FINGERS):
        motor, root, tip, joint2 = _load_merged(finger_id)
        order = np.argsort(motor)
        motor_s = motor[order]

        ax.plot(motor_s, root[order], "o-", color="#dc2626", lw=1.5, ms=4, label="root (joint1)")
        ax.plot(
            motor_s,
            joint2[order],
            "s-",
            color="#16a34a",
            lw=1.5,
            ms=4,
            label="joint2 = tip-root",
        )
        ax.plot(motor_s, tip[order], "^-", color="#2563eb", lw=1.5, ms=4, label="tip (cumulative)")

        ax.set_title(FINGER_LABELS[finger_id])
        ax.set_xlabel("motor_raw")
        ax.set_ylabel("angle (deg)")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7)

    plt.tight_layout()
    out = _OUTPUT_DIR / "angle_decomposition.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    for path in (plot_root_vs_joint2(), plot_decomposition()):
        print(path.resolve())


if __name__ == "__main__":
    main()
