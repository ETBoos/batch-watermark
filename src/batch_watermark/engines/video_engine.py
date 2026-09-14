"""Video image-watermark engine via ffmpeg (overlay + optional HW encode)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
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

# Preference order when hardware encoding is requested
HW_ENCODER_CANDIDATES = ("h264_nvenc", "h264_amf", "h264_qsv")
SOFTWARE_ENCODER = "libx264"


def find_ffmpeg() -> Optional[str]:
    """Return path to ffmpeg executable, or None if missing."""
    which = shutil.which("ffmpeg")
    if which:
        return which
    if os.name == "nt":
        for cand in _WIN_FFMPEG_CANDIDATES:
            if cand and os.path.isfile(cand):
                return cand
    for cand in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(cand):
            return cand
    return None


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


@dataclass(frozen=True)
class EncoderChoice:
    name: str
    is_hardware: bool

    @property
    def label_zh(self) -> str:
        if self.name == "h264_nvenc":
            return "NVIDIA NVENC (h264_nvenc)"
        if self.name == "h264_amf":
            return "AMD AMF (h264_amf)"
        if self.name == "h264_qsv":
            return "Intel QSV (h264_qsv)"
        if self.name == SOFTWARE_ENCODER:
            return "软件编码 (libx264)"
        return self.name


_encoder_cache: dict[str, set[str]] = {}


def list_ffmpeg_encoders(ffmpeg_path: Optional[str] = None) -> set[str]:
    """Probe `ffmpeg -encoders` and return encoder names."""
    ff = ffmpeg_path or find_ffmpeg()
    if not ff:
        return set()
    if ff in _encoder_cache:
        return _encoder_cache[ff]
    try:
        proc = subprocess.run(
            [ff, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    names: set[str] = set()
    # Lines look like: " V..... h264_nvenc           NVIDIA NVENC H.264 encoder"
    for line in text.splitlines():
        m = re.match(r"^\s*[VAS][\.A-Z]{5}\s+(\S+)\s+", line)
        if m:
            names.add(m.group(1))
            continue
        # Fallback: bare token match for known encoders
        for cand in (*HW_ENCODER_CANDIDATES, SOFTWARE_ENCODER):
            if re.search(rf"\b{re.escape(cand)}\b", line):
                names.add(cand)
    _encoder_cache[ff] = names
    return names


def clear_encoder_cache() -> None:
    _encoder_cache.clear()


def pick_video_encoder(
    ffmpeg_path: Optional[str] = None,
    *,
    prefer_hw: bool = True,
    vendor_hints: tuple[str, ...] | list[str] | None = None,
) -> EncoderChoice:
    """
    Prefer a working HW H.264 encoder when available and requested.
    Order: vendor-matched HW → other HW → libx264.
    """
    ff = ffmpeg_path or find_ffmpeg()
    available = list_ffmpeg_encoders(ff) if ff else set()
    if not prefer_hw:
        return EncoderChoice(SOFTWARE_ENCODER, False)

    ordered: list[str] = []
    hints = {h.lower() for h in (vendor_hints or ())}
    prefer_map = {
        "nvidia": "h264_nvenc",
        "amd": "h264_amf",
        "intel": "h264_qsv",
    }
    for hint, enc in prefer_map.items():
        if hint in hints and enc not in ordered:
            ordered.append(enc)
    for enc in HW_ENCODER_CANDIDATES:
        if enc not in ordered:
            ordered.append(enc)

    for enc in ordered:
        if enc in available:
            return EncoderChoice(enc, True)
    return EncoderChoice(SOFTWARE_ENCODER, False)


def _overlay_xy_expr(position: Position, margin: int) -> tuple[str, str]:
    m = max(0, int(margin))
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


def _encoder_args(encoder: str) -> list[str]:
    """Return -c:v and quality flags for the chosen encoder."""
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-b:v", "0"]
    if encoder == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]
    if encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", "23"]
    # software
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "23"]


def _build_overlay_cmd(
    ff: str,
    source: Path,
    image_path: str,
    tmp_path: Path,
    settings: WatermarkSettings,
    encoder: str,
) -> list[str]:
    x, y = _overlay_xy_expr(settings.position, settings.margin)
    scale = max(0.01, float(settings.image_scale))
    opacity = max(0.0, min(1.0, float(settings.opacity)))
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
        str(image_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        *_encoder_args(encoder),
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(tmp_path),
    ]
    return cmd


def apply_video_watermark(
    source: Path | str,
    output: Path | str,
    settings: WatermarkSettings,
    *,
    ffmpeg_path: Optional[str] = None,
    prefer_hw_encode: Optional[bool] = None,
    vendor_hints: tuple[str, ...] | list[str] | None = None,
) -> Path:
    """
    Overlay an image watermark onto a video; preserve audio.
    Uses ffmpeg overlay (CPU filter) + optional hardware H.264 encode.
    Atomic write via temp file then os.replace.
    On HW encoder failure, retries once with libx264.
    """
    source = Path(source)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_path or find_ffmpeg()
    if not ff:
        raise RuntimeError(
            "未找到 ffmpeg。请安装后加入 PATH，或参考 README 中的 Windows 常见安装路径。"
        )

    # Product focus: image watermark on video. Text path kept for engine tests only.
    if settings.mode != WatermarkMode.IMAGE:
        raise ValueError("当前版本仅支持图片水印叠加到视频（mode=image）")
    if not settings.image_path or not os.path.isfile(settings.image_path):
        raise FileNotFoundError(f"水印图片不存在: {settings.image_path}")

    use_hw = (
        settings.prefer_hw_encode if prefer_hw_encode is None else prefer_hw_encode
    )
    choice = pick_video_encoder(ff, prefer_hw=use_hw, vendor_hints=vendor_hints)

    fd, tmp_name = tempfile.mkstemp(suffix=output.suffix or ".mp4", dir=str(output.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)

    def _run(encoder: str) -> subprocess.CompletedProcess[str]:
        cmd = _build_overlay_cmd(ff, source, settings.image_path, tmp_path, settings, encoder)
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    try:
        proc = _run(choice.name)
        used = choice.name
        if proc.returncode != 0 and choice.is_hardware:
            # Fallback: software encode
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            fd2, tmp_name2 = tempfile.mkstemp(
                suffix=output.suffix or ".mp4", dir=str(output.parent)
            )
            os.close(fd2)
            tmp_path = Path(tmp_name2)
            proc = _run(SOFTWARE_ENCODER)
            used = SOFTWARE_ENCODER

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            tail = "\n".join(err.splitlines()[-20:])
            raise RuntimeError(f"ffmpeg 失败 (code={proc.returncode}, encoder={used}): {tail}")

        os.replace(tmp_path, output)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return output
