"""image_engine kept as optional helper — minimal smoke (not GUI batch path)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from batch_watermark.engines.image_engine import apply_image_watermark
from batch_watermark.models.settings import Position, WatermarkMode, WatermarkSettings


def test_image_engine_still_overlays_for_helpers(tmp_path: Path):
    """Kept so rendering helpers remain tested; GUI no longer batches image files."""
    src = tmp_path / "base.png"
    mark = tmp_path / "mark.png"
    Image.new("RGB", (100, 80), color=(255, 0, 0)).save(src)
    Image.new("RGBA", (20, 20), color=(0, 255, 0, 200)).save(mark)

    out = tmp_path / "wm.png"
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
