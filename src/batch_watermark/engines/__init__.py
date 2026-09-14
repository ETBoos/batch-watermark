from batch_watermark.engines.image_engine import apply_image_watermark
from batch_watermark.engines.video_engine import apply_video_watermark, ffmpeg_available, find_ffmpeg

__all__ = [
    "apply_image_watermark",
    "apply_video_watermark",
    "ffmpeg_available",
    "find_ffmpeg",
]
