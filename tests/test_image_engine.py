"""Smoke test for image watermark engine."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from batch_watermark.engines.image_engine import apply_image_watermark
from batch_watermark.models.settings import Position, WatermarkMode, WatermarkSettings


def test_text_watermark_produces_output(tmp_path: Path):
    src = tmp_path / "tiny.png"
    Image.new("RGB", (64, 64), color=(30, 144, 255)).save(src)

    out = tmp_path / "out.png"
    settings = WatermarkSettings(
        mode=WatermarkMode.TEXT,
        text="测试",
        font_size=16,
        color="#FFFFFF",
        opacity=0.7,
        rotation=15,
        position=Position.BOTTOM_RIGHT,
        margin=4,
    )
    result = apply_image_watermark(src, out, settings)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0
    with Image.open(out) as im:
        assert im.size == (64, 64)


def test_image_watermark_overlay(tmp_path: Path):
    src = tmp_path / "base.png"
    mark = tmp_path / "mark.png"
    Image.new("RGB", (100, 80), color=(255, 0, 0)).save(src)
    Image.new("RGBA", (20, 20), color=(0, 255, 0, 200)).save(mark)

    out = tmp_path / "wm.jpg"
    settings = WatermarkSettings(
        mode=WatermarkMode.IMAGE,
        image_path=str(mark),
        image_scale=0.3,
        opacity=0.8,
        position=Position.CENTER,
        margin=0,
    )
    apply_image_watermark(src, out, settings)
    assert out.exists()
