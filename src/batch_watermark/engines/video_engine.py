"""Video watermark engine via ffmpeg CLI (subprocess)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

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
    # ffmpeg overlay / drawtext x,y expressions (W/H main, w/h overlay or text_w/text_h)
    table = {
        Position.TOP_LEFT: (f"{m}", f"{m}"),
        Position.TOP_CENTER: (f"(W-w)/2", f"{m}"),
        Position.TOP_RIGHT: (f"W-w-{m}", f"{m}"),
        Position.MIDDLE_LEFT: (f"{m}", f"(H-h)/2"),
        Position.CENTER: ("(W-w)/2", "(H-h)/2"),
        Position.MIDDLE_RIGHT: (f"W-w-{m}", "(H-h)/2"),
        Position.BOTTOM_LEFT: (f"{m}", f"H-h-{m}"),
        Position.BOTTOM_CENTER: ("(W-w)/2", f"H-h-{m}"),
        Position.BOTTOM_RIGHT: (f"W-w-{m}", f"H-h-{m}"),
    }
    return table.get(position, table[Position.BOTTOM_RIGHT])


def _drawtext_xy(position: Position, margin: int) -> tuple[str, str]:
    m = max(0, int(margin))
    table = {
        Position.TOP_LEFT: (f"{m}", f"{m}"),
        Position.TOP_CENTER: ("(w-text_w)/2", f"{m}"),
        Position.TOP_RIGHT: (f"w-text_w-{m}", f"{m}"),
        Position.MIDDLE_LEFT: (f"{m}", "(h-text_h)/2"),
        Position.CENTER: ("(w-text_w)/2", "(h-text_h)/2"),
        Position.MIDDLE_RIGHT: (f"w-text_w-{m}", "(h-text_h)/2"),
        Position.BOTTOM_LEFT: (f"{m}", f"h-text_h-{m}"),
        Position.BOTTOM_CENTER: ("(w-text_w)/2", f"h-text_h-{m}"),
        Position.BOTTOM_RIGHT: (f"w-text_w-{m}", f"h-text_h-{m}"),
    }
    return table.get(position, table[Position.BOTTOM_RIGHT])


def _escape_drawtext(text: str) -> str:
    # Escape for ffmpeg drawtext
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "%%")
    )


def _font_for_ffmpeg(font_path: str) -> Optional[str]:
    if font_path and os.path.isfile(font_path):
        return font_path
    for cand in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.isfile(cand):
            return cand
    return None


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

    try:
        if settings.mode == WatermarkMode.IMAGE:
            if not settings.image_path or not os.path.isfile(settings.image_path):
                raise FileNotFoundError(f"水印图片不存在: {settings.image_path}")
            x, y = _overlay_xy_expr(settings.position, settings.margin)
            # scale overlay relative to main video width
            scale = max(0.01, float(settings.image_scale))
            opacity = max(0.0, min(1.0, float(settings.opacity)))
            # [1:v]scale then format+colorchannelmixer for opacity, overlay
            filter_complex = (
                f"[1:v]scale=iw*{scale}:-1,format=rgba,"
                f"colorchannelmixer=aa={opacity}[wm];"
                f"[0:v][wm]overlay=x={x}:y={y}:format=auto[vout]"
            )
            cmd = [
                ff,
                "-y",
                "-i",
                str(source),
                "-i",
                str(settings.image_path),
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
                str(tmp_path),
            ]
        else:
            text = _escape_drawtext(settings.text or "")
            x, y = _drawtext_xy(settings.position, settings.margin)
            fontfile = _font_for_ffmpeg(settings.font_path)
            # color with opacity: 0xRRGGBB@opacity
            color = settings.color.strip().lstrip("#")
            if len(color) == 3:
                color = "".join(ch * 2 for ch in color)
            if len(color) != 6:
                color = "FFFFFF"
            opacity = max(0.0, min(1.0, float(settings.opacity)))
            fontsize = max(8, int(settings.font_size))
            parts = [
                f"text='{text}'",
                f"fontsize={fontsize}",
                f"fontcolor=0x{color}@{opacity}",
                f"x={x}",
                f"y={y}",
            ]
            if fontfile:
                # Escape path for filter
                ff_path = fontfile.replace("\\", "/").replace(":", "\\:")
                parts.append(f"fontfile='{ff_path}'")
            if settings.rotation:
                # drawtext has no rotation; skip with note — keep simple for reliability
                pass
            vf = "drawtext=" + ":".join(parts)
            cmd = [
                ff,
                "-y",
                "-i",
                str(source),
                "-vf",
                vf,
                "-c:a",
                "copy",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-movflags",
                "+faststart",
                str(tmp_path),
            ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            # Keep last lines for readability
            tail = "\n".join(err.splitlines()[-20:])
            raise RuntimeError(f"ffmpeg 失败 (code={proc.returncode}): {tail}")

        os.replace(tmp_path, output)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return output
