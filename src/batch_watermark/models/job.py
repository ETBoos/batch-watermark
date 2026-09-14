"""Job models for batch video watermark processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class MediaType(str, Enum):
    IMAGE = "image"  # legacy; not used by GUI batch flow
    VIDEO = "video"
    UNKNOWN = "unknown"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
WATERMARK_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def detect_media_type(path: Path) -> MediaType:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    if ext in IMAGE_EXTENSIONS:
        return MediaType.IMAGE
    return MediaType.UNKNOWN


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


@dataclass
class WatermarkJob:
    """A single video watermark job."""

    source: Path
    output: Path
    media_type: MediaType = MediaType.VIDEO
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    error: Optional[str] = None
    job_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = f"{self.source}:{self.output}"
        self.source = Path(self.source)
        self.output = Path(self.output)
