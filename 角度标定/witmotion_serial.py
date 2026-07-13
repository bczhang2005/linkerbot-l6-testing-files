"""WitMotion 串口读取模块（解析 0x55 0x53 角度数据包）。"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Literal

try:
    import serial
except ImportError as exc:
    raise ImportError(
        "需要 pyserial 才能自动读取 WitMotion。请执行: pip install pyserial"
    ) from exc

AxisName = Literal["roll", "pitch", "yaw"]


@dataclass(frozen=True)
class WitMotionAngles:
    roll: float
    pitch: float
    yaw: float
    timestamp: float

    def get_axis(self, axis: AxisName) -> float:
        return {"roll": self.roll, "pitch": self.pitch, "yaw": self.yaw}[axis]


class WitMotionReader:
    """从 WitMotion 串口读取角度。"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 1.0) -> None:
        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> WitMotionReader:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def read_once(self, timeout_sec: float = 2.0) -> WitMotionAngles | None:
        deadline = time.time() + timeout_sec
        buffer = bytearray()

        while time.time() < deadline:
            chunk = self._serial.read(max(1, self._serial.in_waiting or 1))
            if not chunk:
                continue
            buffer.extend(chunk)

            while len(buffer) >= 11:
                if buffer[0] != 0x55:
                    del buffer[0]
                    continue
                if buffer[1] != 0x53:
                    del buffer[0]
                    continue

                packet = bytes(buffer[:11])
                del buffer[:11]
                return _parse_angle_packet(packet)

        return None

    def read_average(
        self,
        samples: int = 20,
        sample_interval_sec: float = 0.05,
        timeout_sec: float = 5.0,
    ) -> WitMotionAngles | None:
        readings: list[WitMotionAngles] = []
        deadline = time.time() + timeout_sec

        while len(readings) < samples and time.time() < deadline:
            sample = self.read_once(timeout_sec=0.5)
            if sample is not None:
                readings.append(sample)
            time.sleep(sample_interval_sec)

        if not readings:
            return None

        return WitMotionAngles(
            roll=sum(item.roll for item in readings) / len(readings),
            pitch=sum(item.pitch for item in readings) / len(readings),
            yaw=sum(item.yaw for item in readings) / len(readings),
            timestamp=time.time(),
        )


def _parse_angle_packet(packet: bytes) -> WitMotionAngles:
    roll_raw = struct.unpack("<h", packet[2:4])[0]
    pitch_raw = struct.unpack("<h", packet[4:6])[0]
    yaw_raw = struct.unpack("<h", packet[6:8])[0]

    scale = 180.0 / 32768.0
    return WitMotionAngles(
        roll=roll_raw * scale,
        pitch=pitch_raw * scale,
        yaw=yaw_raw * scale,
        timestamp=time.time(),
    )
