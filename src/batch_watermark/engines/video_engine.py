"""Video image-watermark engine via ffmpeg (overlay + optional HW encode)."""

from __future__ import annotations

import json
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
HW_ENCODER_CANDIDATES = ("h264_videotoolbox", "h264_nvenc", "h264_amf", "h264_qsv")
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


def find_ffprobe(ffmpeg_path: Optional[str] = None) -> Optional[str]:
    """Locate ffprobe next to ffmpeg, or on PATH."""
    if ffmpeg_path:
        cand = Path(ffmpeg_path).with_name("ffprobe")
        if os.name == "nt":
            cand = Path(ffmpeg_path).with_name("ffprobe.exe")
        if cand.is_file():
            return str(cand)
    which = shutil.which("ffprobe")
    if which:
        return which
    ff = find_ffmpeg()
    if ff:
        cand = Path(ff).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if cand.is_file():
            return str(cand)
    return None


def probe_video_size(source: Path | str, ffmpeg_path: Optional[str] = None) -> tuple[int, int]:
    """Return display width/height of the first video stream (fallback: coded size)."""
    source = Path(source)
    probe = find_ffprobe(ffmpeg_path)
    if not probe:
        raise RuntimeError("未找到 ffprobe，无法按视频宽度缩放水印。请安装完整 ffmpeg 套件。")
    cmd = [
        probe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:stream_side_data=rotation",
        "-of",
        "json",
        str(source),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"ffprobe 失败: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {(proc.stderr or proc.stdout or '').strip()}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"无法读取视频尺寸: {source}")
    st = streams[0]
    w = int(st.get("width") or 0)
    h = int(st.get("height") or 0)
    if w <= 0 or h <= 0:
        raise RuntimeError(f"无效视频尺寸 {w}x{h}: {source}")
    # Honor rotation metadata when present (90/270 swap)
    rot = 0
    for sd in st.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                rot = abs(int(float(sd["rotation"])))
            except (TypeError, ValueError):
                rot = 0
    tags = st.get("tags") or {}
    if not rot and "rotate" in tags:
        try:
            rot = abs(int(float(tags["rotate"])))
        except (TypeError, ValueError):
            rot = 0
    if rot % 180 == 90:
        w, h = h, w
    return w, h


def watermark_target_width(video_width: int, image_scale: float) -> int:
    """Watermark width in pixels = relative scale × video frame width."""
    return max(1, int(round(int(video_width) * max(0.01, float(image_scale)))))

@dataclass(frozen=True)
class EncoderChoice:
    name: str
    is_hardware: bool

    @property
    def label_zh(self) -> str:
        if self.name == "h264_videotoolbox":
            return "Apple VideoToolbox 硬件编码 (h264_videotoolbox)"
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
        "apple": "h264_videotoolbox",
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
    if encoder == "h264_videotoolbox":
        # q:v 1-100 (lower = higher quality). ~45 balances clarity/speed on Apple Silicon.
        return [
            "-c:v",
            "h264_videotoolbox",
            "-allow_sw",
            "1",
            "-q:v",
            "45",
        ]
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-b:v", "0"]
    if encoder == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]
    if encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", "23"]
    # software fallback — veryfast is much quicker than medium on Mac CPU
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def _build_overlay_cmd(
    ff: str,
    source: Path,
    image_path: str,
    tmp_path: Path,
    settings: WatermarkSettings,
    encoder: str,
    *,
    video_width: Optional[int] = None,
) -> list[str]:
    x, y = _overlay_xy_expr(settings.position, settings.margin)
    opacity = max(0.0, min(1.0, float(settings.opacity)))
    # Scale relative to VIDEO frame width (not watermark PNG width).
    # Old bug: scale=iw*scale used watermark's iw → same PNG pixels on every
    # video, so low-res clips looked huge and high-res clips looked tiny.
    if video_width is None:
        video_width, _ = probe_video_size(source, ffmpeg_path=ff)
    target_w = watermark_target_width(video_width, settings.image_scale)
    filter_complex = (
        f"[1:v]scale={target_w}:-1,format=rgba,"
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

    video_w, _video_h = probe_video_size(source, ffmpeg_path=ff)

    fd, tmp_name = tempfile.mkstemp(suffix=output.suffix or ".mp4", dir=str(output.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)

    def _run(encoder: str) -> subprocess.CompletedProcess[str]:
        cmd = _build_overlay_cmd(
            ff,
            source,
            settings.image_path,
            tmp_path,
            settings,
            encoder,
            video_width=video_w,
        )
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
