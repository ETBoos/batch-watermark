"""Input collection should only pick videos."""

from __future__ import annotations

from pathlib import Path

from batch_watermark.core.queue import build_jobs, collect_input_files


def test_collect_skips_images(tmp_path: Path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"y")
    (tmp_path / "c.mov").write_bytes(b"z")
    files = collect_input_files([tmp_path])
    names = sorted(p.name for p in files)
    assert names == ["a.mp4", "c.mov"]


def test_build_jobs_video_only(tmp_path: Path):
    src = tmp_path / "clip.mkv"
    src.write_bytes(b"v")
    out_dir = tmp_path / "out"
    jobs = build_jobs([src, tmp_path / "nope.jpg"], out_dir)
    assert len(jobs) == 1
    assert jobs[0].source.name == "clip.mkv"
