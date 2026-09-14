"""Worker budget from CPU utilization ratio and available RAM."""

from __future__ import annotations

import math
from dataclasses import dataclass

from batch_watermark.core.hardware import HardwareInfo, detect_hardware

# Rough per-worker RAM assumptions (bytes)
_IMAGE_WORKER_RAM = 256 * 1024 * 1024  # 256 MiB
_VIDEO_WORKER_RAM = 1024 * 1024 * 1024  # 1 GiB
_LOW_RAM_THRESHOLD = 2 * 1024 * 1024 * 1024  # 2 GiB available → throttle
_VIDEO_MAX_WORKERS_CAP = 2


@dataclass(frozen=True)
class WorkerBudget:
    image_workers: int
    video_workers: int
    cpu_ratio: float
    logical_cores: int
    available_ram_bytes: int


def compute_worker_budget(
    cpu_utilization_percent: int,
    hardware: HardwareInfo | None = None,
    *,
    video_max_cap: int = _VIDEO_MAX_WORKERS_CAP,
) -> WorkerBudget:
    """
    workers = max(1, floor(cpu_count * ratio)); reduce if low RAM.
    Video concurrency capped lower (ffmpeg is heavy).
    """
    hw = hardware or detect_hardware()
    ratio = max(0.10, min(1.0, cpu_utilization_percent / 100.0))
    base = max(1, math.floor(hw.logical_cores * ratio))

    # Low RAM: reduce image workers
    image_workers = base
    if hw.available_ram_bytes < _LOW_RAM_THRESHOLD:
        ram_limited = max(1, hw.available_ram_bytes // _IMAGE_WORKER_RAM)
        image_workers = max(1, min(base, ram_limited))
    else:
        ram_fit = max(1, hw.available_ram_bytes // _IMAGE_WORKER_RAM)
        image_workers = max(1, min(base, ram_fit))

    # Video: min(workers, cap) and RAM-aware
    video_ram_fit = max(1, hw.available_ram_bytes // _VIDEO_WORKER_RAM)
    video_workers = max(1, min(image_workers, video_max_cap, video_ram_fit))

    return WorkerBudget(
        image_workers=image_workers,
        video_workers=video_workers,
        cpu_ratio=ratio,
        logical_cores=hw.logical_cores,
        available_ram_bytes=hw.available_ram_bytes,
    )
