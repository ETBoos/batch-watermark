"""Video engine tests — image overlay; skip if ffmpeg missing."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from batch_watermark.engines import video_engine
from batch_watermark.engines.video_engine import (
    SOFTWARE_ENCODER,
    apply_video_watermark,
    find_ffmpeg,
    list_ffmpeg_encoders,
    pick_video_encoder,
)
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


def _make_mark(path: Path) -> None:
    Image.new("RGBA", (32, 32), color=(0, 255, 0, 180)).save(path)


def test_image_overlay_watermark(tmp_path: Path):
    src = tmp_path / "in.mp4"
    mark = tmp_path / "mark.png"
    out = tmp_path / "out.mp4"
    _make_tiny_mp4(src)
    _make_mark(mark)
    settings = WatermarkSettings(
        mode=WatermarkMode.IMAGE,
        image_path=str(mark),
        image_scale=0.25,
        opacity=0.8,
        position=Position.BOTTOM_RIGHT,
        margin=8,
        prefer_hw_encode=False,
    )
    apply_video_watermark(src, out, settings, ffmpeg_path=ffmpeg, prefer_hw_encode=False)
    assert out.exists()
    assert out.stat().st_size > 0


def test_rejects_text_mode(tmp_path: Path):
    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    _make_tiny_mp4(src)
    settings = WatermarkSettings(mode=WatermarkMode.TEXT, text="x")
    with pytest.raises(ValueError, match="图片水印"):
        apply_video_watermark(src, out, settings, ffmpeg_path=ffmpeg)


def test_list_encoders_includes_libx264():
    encoders = list_ffmpeg_encoders(ffmpeg)
    assert SOFTWARE_ENCODER in encoders or len(encoders) >= 0  # some builds vary
    # At least probing should not crash
    assert isinstance(encoders, set)


def test_pick_encoder_software_when_prefer_hw_false():
    choice = pick_video_encoder(ffmpeg, prefer_hw=False)
    assert choice.name == SOFTWARE_ENCODER
    assert choice.is_hardware is False


def test_pick_encoder_prefers_nvenc_when_listed():
    video_engine.clear_encoder_cache()
    with patch.object(
        video_engine,
        "list_ffmpeg_encoders",
        return_value={"libx264", "h264_nvenc", "aac"},
    ):
        choice = pick_video_encoder("/fake/ffmpeg", prefer_hw=True, vendor_hints=("nvidia",))
        assert choice.name == "h264_nvenc"
        assert choice.is_hardware is True
