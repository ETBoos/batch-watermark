"""Persisted application settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QSettings


class WatermarkMode(str, Enum):
    TEXT = "text"
    IMAGE = "image"


class Position(str, Enum):
    """9-grid watermark position."""

    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    MIDDLE_LEFT = "middle_left"
    CENTER = "center"
    MIDDLE_RIGHT = "middle_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


POSITION_LABELS_ZH = {
    Position.TOP_LEFT: "左上",
    Position.TOP_CENTER: "上中",
    Position.TOP_RIGHT: "右上",
    Position.MIDDLE_LEFT: "左中",
    Position.CENTER: "正中",
    Position.MIDDLE_RIGHT: "右中",
    Position.BOTTOM_LEFT: "左下",
    Position.BOTTOM_CENTER: "下中",
    Position.BOTTOM_RIGHT: "右下",
}


@dataclass
class WatermarkSettings:
    mode: WatermarkMode = WatermarkMode.TEXT
    text: str = "水印"
    font_path: str = ""
    font_size: int = 36
    color: str = "#FFFFFF"
    opacity: float = 0.5  # 0.0–1.0
    rotation: float = 0.0  # degrees
    image_path: str = ""
    image_scale: float = 0.2  # relative to base width
    position: Position = Position.BOTTOM_RIGHT
    margin: int = 20
    cpu_utilization: int = 90  # 10–100
    max_retries: int = 3
    output_dir: str = ""
    last_input_dir: str = ""


@dataclass
class AppSettings:
    watermark: WatermarkSettings = field(default_factory=WatermarkSettings)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self.watermark)
        d["mode"] = self.watermark.mode.value
        d["position"] = self.watermark.position.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        wm = WatermarkSettings()
        if "mode" in data:
            try:
                wm.mode = WatermarkMode(data["mode"])
            except ValueError:
                pass
        if "position" in data:
            try:
                wm.position = Position(data["position"])
            except ValueError:
                pass
        for key in (
            "text",
            "font_path",
            "font_size",
            "color",
            "opacity",
            "rotation",
            "image_path",
            "image_scale",
            "margin",
            "cpu_utilization",
            "max_retries",
            "output_dir",
            "last_input_dir",
        ):
            if key in data and data[key] is not None:
                setattr(wm, key, data[key])
        # Clamp
        wm.cpu_utilization = max(10, min(100, int(wm.cpu_utilization)))
        wm.opacity = max(0.0, min(1.0, float(wm.opacity)))
        wm.max_retries = max(0, int(wm.max_retries))
        return cls(watermark=wm)


def _config_dir() -> Path:
    import sys

    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "batch_watermark"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "batch_watermark"
    else:
        base = Path.home() / ".config" / "batch_watermark"
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_json_path() -> Path:
    return _config_dir() / "settings.json"


def save_settings(settings: AppSettings) -> None:
    path = settings_json_path()
    path.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    # Also mirror into QSettings for convenience
    qs = QSettings("ETBoos", "batch_watermark")
    for k, v in settings.to_dict().items():
        qs.setValue(k, v)
    qs.sync()


def load_settings() -> AppSettings:
    path = settings_json_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return AppSettings.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    # Fallback: QSettings
    qs = QSettings("ETBoos", "batch_watermark")
    data: dict[str, Any] = {}
    for key in qs.allKeys():
        data[str(key)] = qs.value(key)
    if data:
        # QSettings may return strings for numbers
        for num_key in ("font_size", "margin", "cpu_utilization", "max_retries"):
            if num_key in data:
                try:
                    data[num_key] = int(data[num_key])
                except (TypeError, ValueError):
                    pass
        for float_key in ("opacity", "rotation", "image_scale"):
            if float_key in data:
                try:
                    data[float_key] = float(data[float_key])
                except (TypeError, ValueError):
                    pass
        return AppSettings.from_dict(data)
    return AppSettings()
