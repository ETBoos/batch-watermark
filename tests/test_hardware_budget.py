"""Unit tests for hardware detection and worker budget."""

from __future__ import annotations

from batch_watermark.core.budget import compute_worker_budget
from batch_watermark.core.hardware import HardwareInfo, detect_hardware


def test_detect_hardware_positive():
    hw = detect_hardware()
    assert hw.logical_cores >= 1
    assert hw.physical_cores >= 1
    assert hw.total_ram_bytes > 0
    assert hw.available_ram_bytes > 0


def test_budget_default_90_percent():
    hw = HardwareInfo(
        physical_cores=4,
        logical_cores=8,
        total_ram_bytes=16 * 1024**3,
        available_ram_bytes=8 * 1024**3,
    )
    budget = compute_worker_budget(90, hardware=hw)
    assert budget.image_workers == max(1, int(8 * 0.9))  # floor(7.2)=7
    assert budget.image_workers == 7
    assert 1 <= budget.video_workers <= 2
    assert budget.video_workers <= budget.image_workers


def test_budget_low_ram_reduces_workers():
    hw = HardwareInfo(
        physical_cores=8,
        logical_cores=16,
        total_ram_bytes=4 * 1024**3,
        available_ram_bytes=1 * 1024**3,  # below 2 GiB threshold
    )
    budget = compute_worker_budget(100, hardware=hw)
    # RAM limited: 1GiB // 256MiB = 4, but also low-RAM path
    assert budget.image_workers <= 4
    assert budget.image_workers >= 1
    assert budget.video_workers == 1  # 1GiB // 1GiB = 1, and cap 2


def test_budget_min_one_worker():
    hw = HardwareInfo(
        physical_cores=1,
        logical_cores=1,
        total_ram_bytes=512 * 1024**2,
        available_ram_bytes=200 * 1024**2,
    )
    budget = compute_worker_budget(10, hardware=hw)
    assert budget.image_workers >= 1
    assert budget.video_workers >= 1
