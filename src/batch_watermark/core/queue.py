"""Batch job queue orchestration — video files with image watermarks."""

from __future__ import annotations

import os
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from batch_watermark.core.budget import WorkerBudget, compute_worker_budget
from batch_watermark.core.hardware import GpuInfo, detect_gpu
from batch_watermark.core.retry import RetryPolicy, run_with_retries
from batch_watermark.engines.video_engine import apply_video_watermark, find_ffmpeg
from batch_watermark.models.job import JobStatus, MediaType, WatermarkJob, is_video_file
from batch_watermark.models.settings import WatermarkMode, WatermarkSettings


ProgressCallback = Callable[[str, float, Optional[float]], None]
JobDoneCallback = Callable[[WatermarkJob], None]
LogCallback = Callable[[str], None]


@dataclass
class BatchResult:
    jobs: list[WatermarkJob] = field(default_factory=list)

    @property
    def failed(self) -> list[WatermarkJob]:
        return [j for j in self.jobs if j.status == JobStatus.FAILED]

    @property
    def succeeded(self) -> list[WatermarkJob]:
        return [j for j in self.jobs if j.status == JobStatus.SUCCESS]


def collect_input_files(paths: list[Path]) -> list[Path]:
    """Collect video files only (mp4/mov/mkv/avi/webm). Folder scan skips non-videos."""
    files: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            if is_video_file(p):
                files.append(p)
        elif p.is_dir():
            for root, _dirs, names in os.walk(p):
                for name in names:
                    fp = Path(root) / name
                    if is_video_file(fp):
                        files.append(fp)
    seen: set[Path] = set()
    out: list[Path] = []
    for f in files:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(f)
    return out


def build_jobs(sources: list[Path], output_dir: Path) -> list[WatermarkJob]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs: list[WatermarkJob] = []
    for src in sources:
        if not is_video_file(src):
            continue
        out = output_dir / src.name
        if out.exists() or any(j.output == out for j in jobs):
            stem, suffix = src.stem, src.suffix
            n = 1
            while True:
                candidate = output_dir / f"{stem}_{n}{suffix}"
                if not candidate.exists() and not any(j.output == candidate for j in jobs):
                    out = candidate
                    break
                n += 1
        jobs.append(WatermarkJob(source=src, output=out, media_type=MediaType.VIDEO))
    return jobs


def _process_video_one(
    job: WatermarkJob,
    settings: WatermarkSettings,
    policy: RetryPolicy,
    ffmpeg_path: Optional[str],
    should_cancel: Callable[[], bool],
    log: LogCallback,
    vendor_hints: tuple[str, ...],
) -> WatermarkJob:
    job.status = JobStatus.RUNNING

    def work() -> None:
        job.attempts += 1
        if not ffmpeg_path:
            raise RuntimeError("未找到 ffmpeg，无法处理视频")
        # Force image mode for product path
        settings.mode = WatermarkMode.IMAGE
        apply_video_watermark(
            job.source,
            job.output,
            settings,
            ffmpeg_path=ffmpeg_path,
            prefer_hw_encode=settings.prefer_hw_encode,
            vendor_hints=vendor_hints,
        )

    try:
        run_with_retries(
            work,
            policy,
            on_retry=lambda attempt, exc, delay: log(
                f"重试 {job.source.name} 第{attempt}次失败: {exc}; {delay:.1f}s 后重试"
            ),
            should_cancel=should_cancel,
        )
        job.status = JobStatus.SUCCESS
        job.error = None
        log(f"完成: {job.source.name} → {job.output.name}")
    except InterruptedError:
        job.status = JobStatus.CANCELLED
        job.error = "已取消"
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.FAILED
        job.error = str(exc)
        log(f"失败: {job.source.name}: {exc}")
    return job


class BatchProcessor:
    """Run video watermark jobs with pause/cancel and progress reporting."""

    def __init__(self) -> None:
        self._paused = False
        self._cancelled = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def cancel(self) -> None:
        self._cancelled = True
        self._paused = False

    def reset_flags(self) -> None:
        self._paused = False
        self._cancelled = False

    def _wait_if_paused(self) -> None:
        while self._paused and not self._cancelled:
            time.sleep(0.1)

    def run(
        self,
        jobs: list[WatermarkJob],
        settings: WatermarkSettings,
        *,
        budget: Optional[WorkerBudget] = None,
        on_progress: Optional[ProgressCallback] = None,
        on_job_done: Optional[JobDoneCallback] = None,
        on_log: Optional[LogCallback] = None,
        gpu: Optional[GpuInfo] = None,
    ) -> BatchResult:
        self.reset_flags()
        log: LogCallback = on_log or (lambda _m: None)
        budget = budget or compute_worker_budget(settings.cpu_utilization)
        policy = RetryPolicy(max_retries=settings.max_retries)
        ffmpeg_path = find_ffmpeg()
        gpu = gpu or detect_gpu()
        vendor_hints = gpu.vendor_hints

        total = len(jobs)
        if total == 0:
            return BatchResult(jobs=jobs)

        log(
            f"硬件预算: 视频并发={budget.video_workers}, "
            f"CPU占比={int(budget.cpu_ratio * 100)}%, 逻辑核心={budget.logical_cores}"
        )
        if settings.prefer_hw_encode:
            log(
                f"显卡编码: 优先开启 | GPU={gpu.summary} | "
                "说明: overlay 滤镜仍主要在 CPU，显卡主要加速编码"
            )
        else:
            log("显卡编码: 已关闭，使用 libx264")
        if not ffmpeg_path:
            log("警告: 未检测到 ffmpeg，视频任务将失败。请安装 ffmpeg 并确保在 PATH 中。")

        done_count = 0
        t0 = time.monotonic()

        def handle_done(job: WatermarkJob) -> None:
            nonlocal done_count
            done_count += 1
            elapsed = time.monotonic() - t0
            rate = done_count / elapsed if elapsed > 0 else 0
            remaining = total - done_count
            eta = remaining / rate if rate > 0 else None
            if on_progress:
                on_progress(f"{done_count}/{total}", done_count / total, eta)
            if on_job_done:
                on_job_done(job)

        workers = max(1, min(budget.video_workers, len(jobs)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map: dict[Future, WatermarkJob] = {}
            for j in jobs:
                self._wait_if_paused()
                if self._cancelled:
                    j.status = JobStatus.CANCELLED
                    j.error = "已取消"
                    handle_done(j)
                    continue
                future_map[
                    pool.submit(
                        _process_video_one,
                        j,
                        settings,
                        policy,
                        ffmpeg_path,
                        lambda: self._cancelled,
                        log,
                        vendor_hints,
                    )
                ] = j
            for fut in as_completed(list(future_map.keys())):
                try:
                    result_job = fut.result()
                except Exception as exc:  # noqa: BLE001
                    result_job = future_map[fut]
                    result_job.status = JobStatus.FAILED
                    result_job.error = str(exc)
                handle_done(result_job)
                if self._cancelled:
                    for f in future_map:
                        f.cancel()
                    break

        for j in jobs:
            if j.status == JobStatus.PENDING:
                j.status = JobStatus.CANCELLED
                j.error = "已取消"

        return BatchResult(jobs=jobs)
