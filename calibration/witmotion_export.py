"""Parse WitMotion PC software export (Data.tsv / txt / csv)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

AXIS_COLUMN_HINTS = {
    "roll": ("角度x", "anglex", "angle x", "roll", "x轴", "x angle"),
    "pitch": ("角度y", "angley", "angle y", "pitch", "y轴", "y angle"),
    "yaw": ("角度z", "anglez", "angle z", "yaw", "z轴", "z angle", "heading"),
}

TIME_COLUMN_HINTS = (
    "time",
    "时间",
    "timestamp",
    "t(s)",
    "t",
    "ms",
    "millisecond",
)


@dataclass(frozen=True)
class WitMotionSeries:
    times_sec: list[float]
    values: list[float]
    axis_column: str
    time_column: str


def _normalize_header(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def _detect_delimiter(sample: str) -> str:
    if sample.count("\t") >= sample.count(","):
        return "\t"
    return ","


def _parse_float(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_clock_time_sec(text: str) -> float | None:
    text = text.strip()
    match = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?$", text)
    if not match:
        return None
    hour, minute, second, fraction = match.groups()
    total = int(hour) * 3600 + int(minute) * 60 + int(second)
    if fraction:
        total += float(f"0.{fraction}")
    return float(total)


def _parse_time_value(text: str, header: str) -> float | None:
    text = text.strip()
    if not text:
        return None

    numeric = _parse_float(text)
    if numeric is not None:
        if "ms" in _normalize_header(header):
            return numeric / 1000.0
        return numeric

    return _parse_clock_time_sec(text)


def _find_column(headers: list[str], hints: tuple[str, ...]) -> int | None:
    normalized = [_normalize_header(item) for item in headers]
    for idx, header in enumerate(normalized):
        for hint in hints:
            if hint in header or header in hint:
                return idx
    return None


def load_witmotion_export(path: Path, axis: str = "roll") -> WitMotionSeries:
    raw_text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [line for line in raw_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"文件为空: {path}")

    delimiter = _detect_delimiter(lines[0])
    header_idx = 0
    for idx, line in enumerate(lines[:20]):
        cells = line.split(delimiter)
        if len(cells) >= 2 and _find_column(cells, AXIS_COLUMN_HINTS[axis]) is not None:
            header_idx = idx
            break

    headers = lines[header_idx].split(delimiter)
    axis_idx = _find_column(headers, AXIS_COLUMN_HINTS[axis])
    if axis_idx is None:
        raise ValueError(
            f"在 {path.name} 中找不到 {axis} 对应列。"
            f"表头为: {headers}"
        )

    time_idx = _find_column(headers, TIME_COLUMN_HINTS)
    times_sec: list[float] = []
    values: list[float] = []

    for line in lines[header_idx + 1 :]:
        cells = [cell.strip() for cell in line.split(delimiter)]
        if len(cells) <= max(axis_idx, time_idx or 0):
            continue
        value = _parse_float(cells[axis_idx])
        if value is None:
            continue

        if time_idx is not None:
            time_value = _parse_time_value(cells[time_idx], headers[time_idx])
            if time_value is None:
                continue
            times_sec.append(time_value)
        else:
            times_sec.append(float(len(values)))

        values.append(value)

    if not values:
        raise ValueError(f"未能从 {path.name} 解析到有效数据。")

    if time_idx is not None and times_sec:
        start_time = times_sec[0]
        times_sec = [time_sec - start_time for time_sec in times_sec]
    time_column = headers[time_idx] if time_idx is not None else "(row_index)"
    return WitMotionSeries(
        times_sec=times_sec,
        values=values,
        axis_column=headers[axis_idx],
        time_column=time_column,
    )


def average_near_time(
    series: WitMotionSeries,
    target_sec: float,
    window_sec: float = 1.0,
) -> float | None:
    selected = [
        value
        for time_sec, value in zip(series.times_sec, series.values, strict=True)
        if abs(time_sec - target_sec) <= window_sec
    ]
    if not selected:
        return None
    return sum(selected) / len(selected)
