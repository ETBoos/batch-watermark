"""Batch job queue orchestration."""

from __future__ import annotations

import os
import time
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from batch_watermark.core.budget import WorkerBudget, compute_worker_budget
from batch_watermark.core.retry import RetryPolicy, run_with_retries
from batch_watermark.engines.image_engine import apply_image_watermark
from batch_watermark.engines.video_engine import apply_video_watermark, find_ffmpeg
from batch_watermark.models.job import JobStatus, MediaType, WatermarkJob, detect_media_type
from batch_watermark.models.settings import WatermarkSettings


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
    files: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            if detect_media_type(p) != MediaType.UNKNOWN:
                files.append(p)
        elif p.is_dir():
            for root, _dirs, names in os.walk(p):
                for name in names:
                    fp = Path(root) / name
                    if detect_media_type(fp) != MediaType.UNKNOWN:
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
        media = detect_media_type(src)
        if media == MediaType.UNKNOWN:
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
        jobs.append(WatermarkJob(source=src, output=out, media_type=media))
    return jobs


def _image_worker(payload: dict) -> dict:
    """Top-level picklable worker for ProcessPoolExecutor."""
    from batch_watermark.models.settings import Position, WatermarkMode

    source = Path(payload["source"])
    output = Path(payload["output"])
    raw = dict(payload["settings"])
    if isinstance(raw.get("mode"), str):
        raw["mode"] = WatermarkMode(raw["mode"])
    if isinstance(raw.get("position"), str):
        raw["position"] = Position(raw["position"])
    settings = WatermarkSettings(**raw)
    max_retries = int(payload.get("max_retries", 3))
    policy = RetryPolicy(max_retries=max_retries)
    attempts = 0
    last_error: Optional[str] = None

    def work() -> None:
        nonlocal attempts
        attempts += 1
        apply_image_watermark(source, output, settings)

    try:
        run_with_retries(work, policy)
        return {
            "source": str(source),
            "output": str(output),
            "status": JobStatus.SUCCESS.value,
            "attempts": attempts,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        last_error = str(exc)
        return {
            "source": str(source),
            "output": str(output),
            "status": JobStatus.FAILED.value,
            "attempts": attempts,
            "error": last_error,
        }


def _process_video_one(
    job: WatermarkJob,
    settings: WatermarkSettings,
    policy: RetryPolicy,
    ffmpeg_path: Optional[str],
    should_cancel: Callable[[], bool],
    log: LogCallback,
) -> WatermarkJob:
    job.status = JobStatus.RUNNING

    def work() -> None:
        job.attempts += 1
        if not ffmpeg_path:
            raise RuntimeError("未找到 ffmpeg，无法处理视频")
        apply_video_watermark(job.source, job.output, settings, ffmpeg_path=ffmpeg_path)

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


def _settings_to_dict(settings: WatermarkSettings) -> dict:
    return {
        "mode": settings.mode.value if hasattr(settings.mode, "value") else settings.mode,
        "text": settings.text,
        "font_path": settings.font_path,
        "font_size": settings.font_size,
        "color": settings.color,
        "opacity": settings.opacity,
        "rotation": settings.rotation,
        "image_path": settings.image_path,
        "image_scale": settings.image_scale,
        "position": settings.position.value if hasattr(settings.position, "value") else settings.position,
        "margin": settings.margin,
        "cpu_utilization": settings.cpu_utilization,
        "max_retries": settings.max_retries,
        "output_dir": settings.output_dir,
        "last_input_dir": settings.last_input_dir,
    }


class BatchProcessor:
    """Run watermark jobs with pause/cancel and progress reporting."""

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
    ) -> BatchResult:
        self.reset_flags()
        log: LogCallback = on_log or (lambda _m: None)
        budget = budget or compute_worker_budget(settings.cpu_utilization)
        policy = RetryPolicy(max_retries=settings.max_retries)
        ffmpeg_path = find_ffmpeg()

        total = len(jobs)
        if total == 0:
            return BatchResult(jobs=jobs)

        log(
            f"硬件预算: 图片并发={budget.image_workers}, "
            f"视频并发={budget.video_workers}, "
            f"CPU占比={int(budget.cpu_ratio * 100)}%, 逻辑核心={budget.logical_cores}"
        )
        if any(j.media_type == MediaType.VIDEO for j in jobs) and not ffmpeg_path:
            log("警告: 未检测到 ffmpeg，视频任务将失败。请安装 ffmpeg 并确保在 PATH 中。")

        done_count = 0
        t0 = time.monotonic()
        job_by_source = {str(j.source.resolve()): j for j in jobs}

        image_jobs = [j for j in jobs if j.media_type == MediaType.IMAGE]
        video_jobs = [j for j in jobs if j.media_type == MediaType.VIDEO]
        other_jobs = [j for j in jobs if j.media_type == MediaType.UNKNOWN]
        for j in other_jobs:
            j.status = JobStatus.FAILED
            j.error = "不支持的文件类型"
            done_count += 1
            if on_job_done:
                on_job_done(j)

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

        # --- Images via ProcessPoolExecutor ---
        if image_jobs and not self._cancelled:
            workers = max(1, min(budget.image_workers, len(image_jobs)))
            settings_dict = _settings_to_dict(settings)
            payloads = []
            for j in image_jobs:
                j.status = JobStatus.RUNNING
                payloads.append(
                    {
                        "source": str(j.source),
                        "output": str(j.output),
                        "settings": settings_dict,
                        "max_retries": settings.max_retries,
                    }
                )
            try:
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    future_map: dict[Future, WatermarkJob] = {}
                    for j, payload in zip(image_jobs, payloads):
                        self._wait_if_paused()
                        if self._cancelled:
                            j.status = JobStatus.CANCELLED
                            j.error = "已取消"
                            handle_done(j)
                            continue
                        future_map[pool.submit(_image_worker, payload)] = j

                    for fut in as_completed(list(future_map.keys())):
                        job = future_map[fut]
                        try:
                            result = fut.result()
                            job.attempts = int(result.get("attempts") or 0)
                            status = result.get("status")
                            if status == JobStatus.SUCCESS.value:
                                job.status = JobStatus.SUCCESS
                                job.error = None
                                log(f"完成: {job.source.name} → {job.output.name}")
                            else:
                                job.status = JobStatus.FAILED
                                job.error = result.get("error") or "未知错误"
                                log(f"失败: {job.source.name}: {job.error}")
                        except Exception as exc:  # noqa: BLE001
                            job.status = JobStatus.FAILED
                            job.error = str(exc)
                            log(f"失败: {job.source.name}: {exc}")
                        handle_done(job)
                        if self._cancelled:
                            for f in future_map:
                                f.cancel()
                            break
            except Exception as exc:  # noqa: BLE001 — fallback to threads if spawn fails
                log(f"进程池不可用 ({exc})，回退到线程池处理图片…")
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futs = []
                    for j in image_jobs:
                        if j.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED):
                            continue

                        def _t(job: WatermarkJob = j) -> WatermarkJob:
                            job.status = JobStatus.RUNNING

                            def work() -> None:
                                job.attempts += 1
                                apply_image_watermark(job.source, job.output, settings)

                            try:
                                run_with_retries(
                                    work,
                                    policy,
                                    should_cancel=lambda: self._cancelled,
                                )
                                job.status = JobStatus.SUCCESS
                                job.error = None
                                log(f"完成: {job.source.name} → {job.output.name}")
                            except InterruptedError:
                                job.status = JobStatus.CANCELLED
                                job.error = "已取消"
                            except Exception as e:  # noqa: BLE001
                                job.status = JobStatus.FAILED
                                job.error = str(e)
                                log(f"失败: {job.source.name}: {e}")
                            return job

                        futs.append(pool.submit(_t))
                    for fut in as_completed(futs):
                        handle_done(fut.result())

        # --- Videos via ThreadPool (ffmpeg subprocess is already parallel) ---
        if video_jobs and not self._cancelled:
            workers = max(1, min(budget.video_workers, len(video_jobs)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map2: dict[Future, WatermarkJob] = {}
                for j in video_jobs:
                    self._wait_if_paused()
                    if self._cancelled:
                        j.status = JobStatus.CANCELLED
                        j.error = "已取消"
                        handle_done(j)
                        continue
                    future_map2[
                        pool.submit(
                            _process_video_one,
                            j,
                            settings,
                            policy,
                            ffmpeg_path,
                            lambda: self._cancelled,
                            log,
                        )
                    ] = j
                for fut in as_completed(list(future_map2.keys())):
                    try:
                        result_job = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        result_job = future_map2[fut]
                        result_job.status = JobStatus.FAILED
                        result_job.error = str(exc)
                    handle_done(result_job)
                    if self._cancelled:
                        for f in future_map2:
                            f.cancel()
                        break

        for j in jobs:
            if j.status == JobStatus.PENDING:
                j.status = JobStatus.CANCELLED
                j.error = "已取消"

        _ = job_by_source  # reserved for future mapping
        return BatchResult(jobs=jobs)
