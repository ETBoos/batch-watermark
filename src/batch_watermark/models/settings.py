"""Persisted application settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class WatermarkMode(str, Enum):
    TEXT = "text"  # retained for engine helpers / legacy settings
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
    mode: WatermarkMode = WatermarkMode.IMAGE
    text: str = ""  # unused in GUI (legacy)
    font_path: str = ""
    font_size: int = 36
    color: str = "#FFFFFF"
    opacity: float = 0.5  # 0.0–1.0
    rotation: float = 0.0  # degrees (image_engine helper)
    image_path: str = ""
    image_scale: float = 0.2  # relative to base width
    position: Position = Position.BOTTOM_RIGHT
    margin: int = 20
    cpu_utilization: int = 90  # 10–100
    max_retries: int = 3
    output_dir: str = ""
    last_input_dir: str = ""
    prefer_hw_encode: bool = True


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
        # Product is image-watermark on video; coerce legacy text mode.
        if wm.mode != WatermarkMode.IMAGE:
            wm.mode = WatermarkMode.IMAGE
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
            "prefer_hw_encode",
        ):
            if key in data and data[key] is not None:
                setattr(wm, key, data[key])
        wm.cpu_utilization = max(10, min(100, int(wm.cpu_utilization)))
        wm.opacity = max(0.0, min(1.0, float(wm.opacity)))
        wm.max_retries = max(0, int(wm.max_retries))
        if isinstance(wm.prefer_hw_encode, str):
            wm.prefer_hw_encode = wm.prefer_hw_encode.strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        else:
            wm.prefer_hw_encode = bool(wm.prefer_hw_encode)
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
    try:
        from PySide6.QtCore import QSettings

        qs = QSettings("ETBoos", "batch_watermark")
        for k, v in settings.to_dict().items():
            qs.setValue(k, v)
        qs.sync()
    except Exception:
        pass


def load_settings() -> AppSettings:
    path = settings_json_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return AppSettings.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    try:
        from PySide6.QtCore import QSettings
    except Exception:
        return AppSettings()
    qs = QSettings("ETBoos", "batch_watermark")
    data: dict[str, Any] = {}
    for key in qs.allKeys():
        data[str(key)] = qs.value(key)
    if data:
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
        if "prefer_hw_encode" in data:
            v = data["prefer_hw_encode"]
            if isinstance(v, str):
                data["prefer_hw_encode"] = v.strip().lower() in ("1", "true", "yes", "on")
            else:
                data["prefer_hw_encode"] = bool(v)
        return AppSettings.from_dict(data)
    return AppSettings()
