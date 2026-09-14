"""Image watermark engine using Pillow."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from batch_watermark.models.settings import Position, WatermarkMode, WatermarkSettings


def _parse_color(color: str, opacity: float) -> Tuple[int, int, int, int]:
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        r, g, b = 255, 255, 255
    else:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    alpha = max(0, min(255, int(round(opacity * 255))))
    return r, g, b, alpha


def _load_font(font_path: str, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidates: list[str] = []
    if font_path:
        candidates.append(font_path)
    # Cross-platform fallbacks (Chinese-capable where possible)
    candidates.extend(
        [
            # macOS
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            # Windows
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            # Linux
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _position_xy(
    base_w: int,
    base_h: int,
    mark_w: int,
    mark_h: int,
    position: Position,
    margin: int,
) -> Tuple[int, int]:
    m = max(0, margin)
    if position == Position.TOP_LEFT:
        return m, m
    if position == Position.TOP_CENTER:
        return (base_w - mark_w) // 2, m
    if position == Position.TOP_RIGHT:
        return base_w - mark_w - m, m
    if position == Position.MIDDLE_LEFT:
        return m, (base_h - mark_h) // 2
    if position == Position.CENTER:
        return (base_w - mark_w) // 2, (base_h - mark_h) // 2
    if position == Position.MIDDLE_RIGHT:
        return base_w - mark_w - m, (base_h - mark_h) // 2
    if position == Position.BOTTOM_LEFT:
        return m, base_h - mark_h - m
    if position == Position.BOTTOM_CENTER:
        return (base_w - mark_w) // 2, base_h - mark_h - m
    # BOTTOM_RIGHT default
    return base_w - mark_w - m, base_h - mark_h - m


def _make_text_overlay(settings: WatermarkSettings) -> Image.Image:
    font = _load_font(settings.font_path, settings.font_size)
    # Measure text
    tmp = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0, 0), settings.text or " ", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 4
    overlay = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rgba = _parse_color(settings.color, settings.opacity)
    draw.text((pad - bbox[0], pad - bbox[1]), settings.text or "", font=font, fill=rgba)
    if settings.rotation:
        overlay = overlay.rotate(settings.rotation, expand=True, resample=Image.Resampling.BICUBIC)
    return overlay


def _make_image_overlay(settings: WatermarkSettings, base_w: int) -> Image.Image:
    if not settings.image_path or not os.path.isfile(settings.image_path):
        raise FileNotFoundError(f"水印图片不存在: {settings.image_path}")
    mark = Image.open(settings.image_path).convert("RGBA")
    target_w = max(1, int(base_w * max(0.01, settings.image_scale)))
    ratio = target_w / mark.width
    target_h = max(1, int(mark.height * ratio))
    mark = mark.resize((target_w, target_h), Image.Resampling.LANCZOS)
    # Apply opacity
    if settings.opacity < 1.0:
        alpha = mark.split()[3]
        alpha = alpha.point(lambda p: int(p * settings.opacity))
        mark.putalpha(alpha)
    if settings.rotation:
        mark = mark.rotate(settings.rotation, expand=True, resample=Image.Resampling.BICUBIC)
    return mark


def apply_image_watermark(
    source: Path | str,
    output: Path | str,
    settings: WatermarkSettings,
) -> Path:
    """
    Apply watermark to an image and write atomically (temp then replace).
    """
    source = Path(source)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as im:
        base = im.convert("RGBA")

    if settings.mode == WatermarkMode.IMAGE:
        overlay = _make_image_overlay(settings, base.width)
    else:
        overlay = _make_text_overlay(settings)

    x, y = _position_xy(
        base.width, base.height, overlay.width, overlay.height, settings.position, settings.margin
    )
    composed = base.copy()
    composed.alpha_composite(overlay, dest=(x, y))

    # Preserve format; default PNG if unknown
    suffix = output.suffix.lower()
    save_kwargs: dict = {}
    if suffix in {".jpg", ".jpeg"}:
        to_save = composed.convert("RGB")
        save_kwargs["quality"] = 95
        save_kwargs["optimize"] = True
        fmt = "JPEG"
    elif suffix == ".webp":
        to_save = composed
        save_kwargs["quality"] = 90
        fmt = "WEBP"
    elif suffix in {".tif", ".tiff"}:
        to_save = composed
        fmt = "TIFF"
    elif suffix == ".bmp":
        to_save = composed.convert("RGB")
        fmt = "BMP"
    else:
        to_save = composed
        fmt = "PNG"

    fd, tmp_name = tempfile.mkstemp(suffix=output.suffix or ".png", dir=str(output.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        to_save.save(tmp_path, format=fmt, **save_kwargs)
        os.replace(tmp_path, output)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return output
