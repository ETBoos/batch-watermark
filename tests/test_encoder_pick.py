from batch_watermark.engines.video_engine import pick_video_encoder


def test_pick_software_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "batch_watermark.engines.video_engine.list_ffmpeg_encoders",
        lambda *_a, **_k: {"libx264", "h264_videotoolbox", "h264_nvenc"},
    )
    choice = pick_video_encoder("/fake/ffmpeg", prefer_hw=False)
    assert choice.name == "libx264"
    assert choice.is_hardware is False


def test_pick_videotoolbox_for_apple(monkeypatch):
    monkeypatch.setattr(
        "batch_watermark.engines.video_engine.list_ffmpeg_encoders",
        lambda *_a, **_k: {"libx264", "h264_videotoolbox", "h264_nvenc"},
    )
    choice = pick_video_encoder(
        "/fake/ffmpeg", prefer_hw=True, vendor_hints=("apple",)
    )
    assert choice.name == "h264_videotoolbox"
    assert choice.is_hardware is True
    assert "VideoToolbox" in choice.label_zh
