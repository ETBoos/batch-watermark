"""GPU detection smoke tests (best-effort, no hardware required)."""

from __future__ import annotations

from batch_watermark.core.hardware import detect_gpu, detect_hardware


def test_detect_hardware_still_works():
    hw = detect_hardware()
    assert hw.logical_cores >= 1


def test_detect_gpu_returns_struct():
    gpu = detect_gpu()
    assert isinstance(gpu.names, tuple)
    assert isinstance(gpu.summary, str)
