"""Video engine tests — skip if ffmpeg missing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from batch_watermark.engines.video_engine import apply_video_watermark, find_ffmpeg
from batch_watermark.models.settings import Position, WatermarkMode, WatermarkSettings

ffmpeg = find_ffmpeg()
pytestmark = pytest.mark.skipif(ffmpeg is None, reason="ffmpeg not installed")


def _make_tiny_mp4(path: Path) -> None:
    assert ffmpeg
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=160x120:d=0.5",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=0.5",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip(f"cannot generate sample video: {proc.stderr[-200:]}")


def test_drawtext_watermark(tmp_path: Path):
    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    _make_tiny_mp4(src)
    settings = WatermarkSettings(
        mode=WatermarkMode.TEXT,
        text="WM",
        font_size=18,
        color="#FFFFFF",
        opacity=0.8,
        position=Position.BOTTOM_RIGHT,
        margin=8,
    )
    apply_video_watermark(src, out, settings, ffmpeg_path=ffmpeg)
    assert out.exists()
    assert out.stat().st_size > 0
