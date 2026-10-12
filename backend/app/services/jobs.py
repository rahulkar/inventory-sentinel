"""Shared background job runner: one worker thread, FIFO queue, polled progress.

Every heavy operation (generate, upload, train, detect, retrain, export) is submitted here. Running one job at
a time keeps memory bounded on a laptop and makes progress and ETAs meaningful.
"""
from __future__ import annotations

import gc
import queue
import threading
import time
import traceback
from collections import OrderedDict
from typing import Any, Callable

from app import config
from app.schemas import Job, JobStep, JobType
from app.services.storage import new_id, now_iso

Runner = Callable[["JobContext"], dict[str, Any] | None]


class JobCancelled(Exception):
    """Raised inside a job when the user cancelled it."""


_lock = threading.RLock()
_jobs: OrderedDict[str, Job] = OrderedDict()
_runners: dict[str, Runner] = {}
_queue: queue.Queue[str] = queue.Queue()
_cancel_flags: set[str] = set()
_started: dict[str, float] = {}
_step_started: dict[str, float] = {}
_worker: threading.Thread | None = None


class JobContext:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id

    def _mut(self, fn: Callable[[Job], None]) -> None:
        with _lock:
            job = _jobs.get(self.job_id)
            if job is not None:
                fn(job)

    def step(self, key: str, label: str) -> None:
        now = time.time()

        def f(job: Job) -> None:
            for s in job.steps:
                if s.status == "running":
                    s.status = "done"
                    s.seconds = round(now - _step_started.get(f"{job.job_id}:{s.key}", now), 1)
            existing = next((s for s in job.steps if s.key == key), None)
            if existing is None:
                existing = JobStep(key=key, label=label)
                job.steps.append(existing)
            existing.status = "running"
            existing.label = label
            _step_started[f"{job.job_id}:{key}"] = now
            job.step = label
            job.message = None

        self._mut(f)

    def progress(self, percent: float, message: str | None = None) -> None:
        def f(job: Job) -> None:
            job.percent = float(max(0.0, min(100.0, percent)))
            if message is not None:
                job.message = message

        self._mut(f)

    def warn(self, text: str) -> None:
        self._mut(lambda job: job.warnings.append(text))

    def detail(self, payload: dict[str, Any]) -> None:
        self._mut(lambda job: setattr(job, "detail", payload))

    def check_cancelled(self) -> None:
        with _lock:
            cancelled = self.job_id in _cancel_flags
        if cancelled:
            raise JobCancelled()


def _refresh_timing(job: Job) -> None:
    start = _started.get(job.job_id)
    if start is None:
        job.elapsed_seconds = 0.0
        job.eta_seconds = job.estimate_seconds
        return
    end = time.time() if job.status == "running" else _finished_at_ts(job)
    job.elapsed_seconds = round(max(0.0, end - start), 1)
    if job.status != "running":
        job.eta_seconds = None
    elif job.percent >= 5:
        job.eta_seconds = round(job.elapsed_seconds * (100 - job.percent) / job.percent, 1)
    elif job.estimate_seconds:
        job.eta_seconds = round(max(0.0, job.estimate_seconds - job.elapsed_seconds), 1)
    else:
        job.eta_seconds = None


_finished_ts: dict[str, float] = {}


def _finished_at_ts(job: Job) -> float:
    return _finished_ts.get(job.job_id, time.time())


def _queue_positions() -> dict[str, int]:
    pos = {}
    n = 0
    for jid, j in _jobs.items():
        if j.status == "queued":
            n += 1
            pos[jid] = n
    return pos


def _snapshot(job: Job) -> Job:
    _refresh_timing(job)
    copy = job.model_copy(deep=True)
    copy.queue_position = _queue_positions().get(job.job_id)
    return copy


def _trim() -> None:
    terminal = [jid for jid, j in _jobs.items() if j.status in ("done", "failed", "cancelled")]
    while len(terminal) > config.JOBS_KEEP:
        jid = terminal.pop(0)
        _jobs.pop(jid, None)
        _started.pop(jid, None)
        _finished_ts.pop(jid, None)
        _cancel_flags.discard(jid)


def _worker_loop() -> None:
    while True:
        job_id = _queue.get()
        try:
            with _lock:
                job = _jobs.get(job_id)
                runner = _runners.pop(job_id, None)
                if job is None or runner is None or job.status != "queued":
                    continue
                job.status = "running"
                job.started_at = now_iso()
                _started[job_id] = time.time()
            ctx = JobContext(job_id)
            try:
                result = runner(ctx)
                with _lock:
                    for s in job.steps:
                        if s.status == "running":
                            s.status = "done"
                            s.seconds = round(time.time() - _step_started.get(f"{job_id}:{s.key}", time.time()), 1)
                    job.status = "done"
                    job.percent = 100.0
                    job.result = result
                    job.step = None
            except JobCancelled:
                with _lock:
                    job.status = "cancelled"
                    job.error = "Cancelled by user."
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                with _lock:
                    job.status = "failed"
                    job.error = f"{type(exc).__name__}: {exc}"
            finally:
                with _lock:
                    job.finished_at = now_iso()
                    _finished_ts[job_id] = time.time()
                    for s in job.steps:
                        if s.status in ("running", "queued") and job.status != "done":
                            s.status = job.status if job.status in ("failed", "cancelled") else s.status
                    _refresh_timing(job)
                    _trim()
                gc.collect()
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_worker_loop, name="sentinel-jobs", daemon=True)
        _worker.start()


def submit(
    type_: JobType,
    title: str,
    run: Runner,
    *,
    params: dict[str, Any] | None = None,
    steps: list[tuple[str, str]] | None = None,
    estimate_seconds: float | None = None,
    job_id: str | None = None,
) -> Job:
    job_id = job_id or new_id("job")
    job = Job(
        job_id=job_id,
        type=type_,
        title=title,
        created_at=now_iso(),
        params=params or {},
        steps=[JobStep(key=k, label=l) for k, l in (steps or [])],
        estimate_seconds=estimate_seconds,
    )
    with _lock:
        _jobs[job_id] = job
        _runners[job_id] = run
        snap = _snapshot(job)
    _ensure_worker()
    _queue.put(job_id)
    return snap


def get(job_id: str) -> Job | None:
    with _lock:
        job = _jobs.get(job_id)
        return _snapshot(job) if job else None


def list_jobs(*, active_only: bool = False, types: list[str] | None = None, limit: int = 50) -> list[Job]:
    with _lock:
        items = []
        for job in reversed(_jobs.values()):
            if active_only and job.status not in ("queued", "running"):
                continue
            if types and job.type not in types:
                continue
            items.append(_snapshot(job))
            if len(items) >= limit:
                break
    return items


def cancel(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return False
        if job.status == "queued":
            job.status = "cancelled"
            job.error = "Cancelled before it started."
            job.finished_at = now_iso()
            _runners.pop(job_id, None)
            return True
        if job.status == "running":
            _cancel_flags.add(job_id)
            return True
        return False


def is_busy() -> bool:
    with _lock:
        return any(j.status in ("queued", "running") for j in _jobs.values())
