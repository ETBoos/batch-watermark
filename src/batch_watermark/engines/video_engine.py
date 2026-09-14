"""Video watermark engine via ffmpeg CLI (subprocess).

Text watermarks are rendered with Pillow to a temporary PNG overlay, then
composited with ffmpeg `overlay`. This avoids depending on ffmpeg builds that
ship `drawtext`/`libfreetype` (many Homebrew and Windows builds omit it).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from batch_watermark.models.settings import Position, WatermarkMode, WatermarkSettings

# Common Windows install locations (also documented in README)
_WIN_FFMPEG_CANDIDATES = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
    os.path.expandvars(r"%USERPROFILE%\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"),
    os.path.expandvars(r"%ChocolateyInstall%\bin\ffmpeg.exe"),
]


def find_ffmpeg() -> Optional[str]:
    """Return path to ffmpeg executable, or None if missing."""
    which = shutil.which("ffmpeg")
    if which:
        return which
    if os.name == "nt":
        for cand in _WIN_FFMPEG_CANDIDATES:
            if cand and os.path.isfile(cand):
                return cand
    # macOS Homebrew
    for cand in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(cand):
            return cand
    return None


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def _overlay_xy_expr(position: Position, margin: int) -> tuple[str, str]:
    m = max(0, int(margin))
    table = {
        Position.TOP_LEFT: (f"{m}", f"{m}"),
        Position.TOP_CENTER: ("(W-w)/2", f"{m}"),
        Position.TOP_RIGHT: (f"W-w-{m}", f"{m}"),
        Position.MIDDLE_LEFT: (f"{m}", "(H-h)/2"),
        Position.CENTER: ("(W-w)/2", "(H-h)/2"),
        Position.MIDDLE_RIGHT: (f"W-w-{m}", "(H-h)/2"),
        Position.BOTTOM_LEFT: (f"{m}", f"H-h-{m}"),
        Position.BOTTOM_CENTER: ("(W-w)/2", f"H-h-{m}"),
        Position.BOTTOM_RIGHT: (f"W-w-{m}", f"H-h-{m}"),
    }
    return table.get(position, table[Position.BOTTOM_RIGHT])


def _load_font(font_path: str, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidates: list[str] = []
    if font_path:
        candidates.append(font_path)
    candidates.extend(
        [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for p in candidates:
        if p and os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _parse_color(color: str, opacity: float) -> tuple[int, int, int, int]:
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        r, g, b = 255, 255, 255
    else:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    alpha = max(0, min(255, int(round(opacity * 255))))
    return r, g, b, alpha


def _render_text_overlay_png(settings: WatermarkSettings, dest: Path) -> Path:
    """Render text watermark to a transparent PNG for ffmpeg overlay."""
    text = settings.text or " "
    fontsize = max(8, int(settings.font_size))
    font = _load_font(settings.font_path, fontsize)
    rgba = _parse_color(settings.color, float(settings.opacity))

    # Measure text box
    dummy = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = max(1, bbox[2] - bbox[0] + 8)
    th = max(1, bbox[3] - bbox[1] + 8)
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((-bbox[0] + 4, -bbox[1] + 4), text, font=font, fill=rgba)

    rotation = float(settings.rotation or 0)
    if abs(rotation) > 0.01:
        img = img.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG")
    return dest


def _run_overlay(
    ff: str,
    source: Path,
    overlay_path: Path,
    output_tmp: Path,
    settings: WatermarkSettings,
    *,
    scale_overlay: bool,
) -> None:
    x, y = _overlay_xy_expr(settings.position, settings.margin)
    if scale_overlay:
        scale = max(0.01, float(settings.image_scale))
        opacity = max(0.0, min(1.0, float(settings.opacity)))
        filter_complex = (
            f"[1:v]scale=iw*{scale}:-1,format=rgba,"
            f"colorchannelmixer=aa={opacity}[wm];"
            f"[0:v][wm]overlay=x={x}:y={y}:format=auto[vout]"
        )
    else:
        # Text PNG already has opacity/rotation baked in
        filter_complex = (
            f"[1:v]format=rgba[wm];"
            f"[0:v][wm]overlay=x={x}:y={y}:format=auto[vout]"
        )
    cmd = [
        ff,
        "-y",
        "-i",
        str(source),
        "-i",
        str(overlay_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output_tmp),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        tail = "\n".join(err.splitlines()[-20:])
        raise RuntimeError(f"ffmpeg 失败 (code={proc.returncode}): {tail}")


def apply_video_watermark(
    source: Path | str,
    output: Path | str,
    settings: WatermarkSettings,
    *,
    ffmpeg_path: Optional[str] = None,
) -> Path:
    """
    Burn text or overlay image watermark; preserve audio.
    Atomic write via temp file then os.replace.
    """
    source = Path(source)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_path or find_ffmpeg()
    if not ff:
        raise RuntimeError(
            "未找到 ffmpeg。请安装后加入 PATH，或参考 README 中的 Windows 常见安装路径。"
        )

    fd, tmp_name = tempfile.mkstemp(suffix=output.suffix or ".mp4", dir=str(output.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    text_overlay: Optional[Path] = None

    try:
        if settings.mode == WatermarkMode.IMAGE:
            if not settings.image_path or not os.path.isfile(settings.image_path):
                raise FileNotFoundError(f"水印图片不存在: {settings.image_path}")
            _run_overlay(
                ff,
                source,
                Path(settings.image_path),
                tmp_path,
                settings,
                scale_overlay=True,
            )
        else:
            tfd, tname = tempfile.mkstemp(suffix=".png", dir=str(output.parent))
            os.close(tfd)
            text_overlay = Path(tname)
            _render_text_overlay_png(settings, text_overlay)
            _run_overlay(
                ff,
                source,
                text_overlay,
                tmp_path,
                settings,
                scale_overlay=False,
            )

        os.replace(tmp_path, output)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        if text_overlay is not None and text_overlay.exists():
            try:
                text_overlay.unlink()
            except OSError:
                pass
    return output
