"""Watermark scale must be relative to video width, not PNG width."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from batch_watermark.engines.video_engine import (
    _build_overlay_cmd,
    find_ffmpeg,
    watermark_target_width,
)
from batch_watermark.models.settings import Position, WatermarkMode, WatermarkSettings

ffmpeg = find_ffmpeg()


def test_target_width_scales_with_video():
    assert watermark_target_width(1920, 0.2) == 384
    assert watermark_target_width(1280, 0.2) == 256
    assert watermark_target_width(640, 0.2) == 128
    # Same settings → proportional to each video (not constant pixels)
    assert watermark_target_width(1920, 0.2) != watermark_target_width(640, 0.2)


@pytest.mark.skipif(ffmpeg is None, reason="ffmpeg not installed")
def test_overlay_cmd_uses_video_relative_pixels(tmp_path: Path):
    mark = tmp_path / "mark.png"
    # Large PNG on purpose — old bug would scale relative to this iw
    Image.new("RGBA", (2000, 400), (255, 0, 0, 200)).save(mark)
    settings = WatermarkSettings(
        mode=WatermarkMode.IMAGE,
        image_path=str(mark),
        image_scale=0.2,
        opacity=0.5,
        position=Position.BOTTOM_RIGHT,
        margin=20,
    )
    src = tmp_path / "dummy.mp4"
    src.write_bytes(b"not-a-real-video")
    cmd = _build_overlay_cmd(
        ffmpeg,
        src,
        str(mark),
        tmp_path / "out.mp4",
        settings,
        "libx264",
        video_width=1280,
    )
    joined = " ".join(cmd)
    # 20% of 1280 = 256 — must appear as absolute scale width
    assert "scale=256:-1" in joined
    # Must NOT use watermark-relative iw*scale form
    assert "scale=iw*" not in joined


def test_same_scale_different_resolutions_proportional():
    """Visual size as fraction of frame is constant across resolutions."""
    s = 0.2
    for w in (640, 1280, 1920, 3840):
        assert abs(watermark_target_width(w, s) / w - s) < 1e-9
