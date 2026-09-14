"""Hardware detection via psutil."""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class HardwareInfo:
    """Detected CPU / RAM snapshot."""

    physical_cores: int
    logical_cores: int
    total_ram_bytes: int
    available_ram_bytes: int

    @property
    def total_ram_gb(self) -> float:
        return self.total_ram_bytes / (1024**3)

    @property
    def available_ram_gb(self) -> float:
        return self.available_ram_bytes / (1024**3)


def detect_hardware() -> HardwareInfo:
    physical = psutil.cpu_count(logical=False) or 1
    logical = psutil.cpu_count(logical=True) or physical
    mem = psutil.virtual_memory()
    return HardwareInfo(
        physical_cores=int(physical),
        logical_cores=int(logical),
        total_ram_bytes=int(mem.total),
        available_ram_bytes=int(mem.available),
    )
