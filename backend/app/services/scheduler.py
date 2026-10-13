"""Scheduled pipelines: at a set time, sync a vendor, (re)train or pick a model, detect, and propose vendor tasks.

A schedule runs as ONE "pipeline" job on the shared job queue: sync, then train (only when retraining), then detect,
then propose. Doing it as a single job means nothing else slips between the steps on the FIFO worker, it cancels as
a unit, and a restart cannot leave a half-finished chain behind.

The engine is a daemon thread started with the app. It ticks every SCHEDULER_TICK_S seconds and starts the schedules
that are due. Missed runs while the app was down collapse into one catch-up run (or are skipped, per schedule). A
schedule never overlaps itself. Vendor tasks from a scheduled run are only *proposed*; a person approves them on the
Schedules page or in the chat, within 72 hours.

Only one engine may run per data directory, so serve the API with a single uvicorn worker.
"""
from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import config
from app.schemas import Job, Schedule, ScheduleIn, ScheduleRun, SchedulerStatus, TrainRequest
from app.services import connectors, jobs, storage

_lock = threading.RLock()
_cache: list[Schedule] | None = None
_thread: threading.Thread | None = None
_stop = threading.Event()
_last_tick: str | None = None
FEED_SOP = "data-feed-failure"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- persistence
def _load() -> list[Schedule]:
    global _cache
    if _cache is None:
        items: list[Schedule] = []
        if config.SCHEDULES_PATH.exists():
            try:
                for d in json.loads(config.SCHEDULES_PATH.read_text(encoding="utf-8")):
                    try:
                        items.append(Schedule(**d))
                    except ValueError:
                        continue
            except ValueError:
                pass
        _cache = items
    return _cache


def _save() -> None:
    config.ensure_dirs()
    storage.atomic_write_text(config.SCHEDULES_PATH, json.dumps([s.model_dump() for s in _load()], indent=1))


def list_all() -> list[Schedule]:
    with _lock:
        return [s.model_copy(deep=True) for s in _load()]


def get(schedule_id: str) -> Schedule:
    with _lock:
        for s in _load():
            if s.id == schedule_id:
                return s.model_copy(deep=True)
    raise LookupError(f"Schedule {schedule_id} not found.")


def validate(body: ScheduleIn) -> ScheduleIn:
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone {body.timezone!r} (use a name like Europe/London).") from exc
    try:
        hh, mm = (int(x) for x in body.frequency.at.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except (ValueError, AssertionError) as exc:
        raise ValueError(f"Time must be HH:MM, got {body.frequency.at!r}.") from exc
    if not body.frequency.days or any(d < 0 or d > 6 for d in body.frequency.days):
        raise ValueError("Pick at least one weekday (0 = Monday ... 6 = Sunday).")
    connectors.get(body.connector_id)
    p = body.pipeline
    if p.model_policy == "fixed":
        if not p.model_id or storage.get_model_summary(p.model_id) is None:
            raise ValueError("Choose a saved model for the 'use this model' policy.")
    if p.model_policy == "retrain":
        from app.services import registry

        bad = [m.key for m in p.train.models if m.key not in registry.REGISTRY or m.key == "reranker"]
        if bad or not p.train.models:
            raise ValueError(f"Choose algorithms from {', '.join(k for k in registry.REGISTRY)}" + (f" (unknown: {', '.join(bad)})." if bad else "."))
    return body


def create(body: ScheduleIn) -> Schedule:
    validate(body)
    now = storage.now_iso()
    s = Schedule(id=storage.new_id("sch"), created_at=now, updated_at=now, **body.model_dump())
    s.next_run_at = _iso(next_run(s, _utcnow()))
    with _lock:
        _load().append(s)
        _save()
    return s.model_copy(deep=True)


def update(schedule_id: str, body: ScheduleIn) -> Schedule:
    validate(body)
    with _lock:
        items = _load()
        for i, s in enumerate(items):
            if s.id == schedule_id:
                data = s.model_dump()
                data.update(body.model_dump())
                data["updated_at"] = storage.now_iso()
                new = Schedule(**data)
                new.next_run_at = _iso(next_run(new, _utcnow()))
                items[i] = new
                _save()
                return new.model_copy(deep=True)
    raise LookupError(f"Schedule {schedule_id} not found.")


def set_enabled(schedule_id: str, enabled: bool) -> Schedule:
    s = get(schedule_id)
    return update(schedule_id, ScheduleIn(**{**s.model_dump(include=set(ScheduleIn.model_fields)), "enabled": enabled}))


def delete(schedule_id: str) -> bool:
    with _lock:
        items = _load()
        keep = [s for s in items if s.id != schedule_id]
        if len(keep) == len(items):
            return False
        items[:] = keep
        _save()
    return True


def _patch(schedule_id: str, **fields: Any) -> None:
    with _lock:
        for s in _load():
            if s.id == schedule_id:
                for k, v in fields.items():
                    setattr(s, k, v)
                _save()
                return


# ---------------------------------------------------------------- timing
def next_run(s: Schedule, after: datetime) -> datetime:
    """The first due time strictly after `after` (UTC), in the schedule's timezone."""
    tz = ZoneInfo(s.timezone)
    local = after.astimezone(tz)
    f = s.frequency
    if f.kind == "interval":
        base = local.replace(hour=0, minute=0, second=0, microsecond=0)
        step = timedelta(hours=f.every_hours)
        t = base
        while t <= local:
            t += step
        while t.weekday() not in f.days:
            t = (t + timedelta(days=1)).replace(hour=0, minute=0)
        return t.astimezone(timezone.utc)
    hh, mm = (int(x) for x in f.at.split(":"))
    days = f.days if f.kind == "weekly" else (f.days or list(range(7)))
    for i in range(0, 8):
        d = (local + timedelta(days=i)).date()
        cand = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
        if cand > local and cand.weekday() in days:
            return cand.astimezone(timezone.utc)
    return (local + timedelta(days=7)).astimezone(timezone.utc)


def describe(s: Schedule | ScheduleIn) -> str:
    f = s.frequency
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = "every day" if sorted(f.days) == list(range(7)) else "weekdays" if sorted(f.days) == list(range(5)) else ", ".join(names[d] for d in sorted(f.days))
    when = f"every {f.every_hours} h ({days})" if f.kind == "interval" else f"{days} at {f.at}"
    p = s.pipeline
    model = {"active": "the model in use", "fixed": f"model {p.model_id}", "retrain": "a fresh " + " + ".join(m.key for m in p.train.models) + " model"}[p.model_policy]
    conn = s.connector_id
    try:
        conn = connectors.get(s.connector_id).name
    except LookupError:
        pass
    parts = [f"{when} {s.timezone}:", f"sync {conn}," if p.sync else "use the latest snapshot,", f"detect with {model}"]
    if p.auto_tasks.enabled:
        parts.append(f", then propose vendor tasks for new {'/'.join(p.auto_tasks.severities)} alerts (up to {p.auto_tasks.max_tasks}, approval needed)")
    text = " ".join(parts).replace(" ,", ",")
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------- run history
def _runs() -> dict[str, ScheduleRun]:
    out: dict[str, ScheduleRun] = {}
    p = config.SCHEDULE_RUNS_PATH
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = ScheduleRun(**json.loads(line))
        except ValueError:
            continue
        out[r.run_id] = r
    return out


def _write_run(r: ScheduleRun) -> ScheduleRun:
    config.ensure_dirs()
    with _lock, config.SCHEDULE_RUNS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(r.model_dump_json() + "\n")
    _patch(r.schedule_id, last_run={k: getattr(r, k) for k in ("run_id", "status", "trigger", "started_at", "finished_at", "error", "error_kind", "new_alerts", "new_critical", "detection_run_id", "proposal_id", "job_id")})
    return r


def list_runs(schedule_id: str | None = None, limit: int = 50) -> list[ScheduleRun]:
    with _lock:
        items = list(_runs().values())
    if schedule_id:
        items = [r for r in items if r.schedule_id == schedule_id]
    items.sort(key=lambda r: r.started_at, reverse=True)
    return items[:limit]


def get_run(run_id: str) -> ScheduleRun:
    r = _runs().get(run_id)
    if r is None:
        raise LookupError(f"Schedule run {run_id} not found.")
    return r


# ---------------------------------------------------------------- launching
def _busy(s: Schedule) -> Job | None:
    jid = (s.last_run or {}).get("job_id")
    if not jid:
        return None
    j = jobs.get(jid)
    return j if j is not None and j.status in ("queued", "running") else None


def launch(s: Schedule, trigger: str) -> tuple[ScheduleRun, Job | None]:
    now = storage.now_iso()
    busy = _busy(s)
    if busy is not None:
        r = ScheduleRun(run_id=storage.new_id("srun"), schedule_id=s.id, schedule_name=s.name, trigger=trigger, status="skipped", started_at=now, finished_at=now,  # type: ignore[arg-type]
                        error=f"The previous run is still {busy.status}.", error_kind="overlap")
        return _write_run(r), None
    job_id = storage.new_id("job")
    r = ScheduleRun(run_id=storage.new_id("srun"), schedule_id=s.id, schedule_name=s.name, trigger=trigger, status="queued", started_at=now, job_id=job_id)  # type: ignore[arg-type]
    _write_run(r)  # before the job exists: the worker may start it at once
    title = f"Scheduled: {s.name}" + (" (run now)" if trigger == "manual" else "")
    job = jobs.submit(
        "pipeline", title, lambda ctx: _pipeline(ctx, s.id, r.run_id),
        params={"schedule_id": s.id, "connector_id": s.connector_id, "schedule_run_id": r.run_id},
        steps=[("sync:capabilities", "Sync: checking the vendor")] if s.pipeline.sync else [], estimate_seconds=_estimate(s), job_id=job_id,
    )
    return r, job


def _estimate(s: Schedule) -> float:
    est = 20.0
    try:
        c = connectors.get(s.connector_id)
        est += (c.last_sync.seconds or 30.0) if c.last_sync else 60.0
    except LookupError:
        pass
    if s.pipeline.model_policy == "retrain":
        from app.services import training

        est += training.estimate_seconds([m.key for m in s.pipeline.train.models], s.pipeline.train.train_sample_size, config.EVAL_NEGATIVES)
    return round(est, 1)


def run_now(schedule_id: str) -> tuple[ScheduleRun, Job | None]:
    s = get(schedule_id)
    return launch(s, "manual")


# ---------------------------------------------------------------- the pipeline (inside one job)
def _pipeline(ctx: jobs.JobContext, schedule_id: str, run_id: str) -> dict[str, Any]:
    from app.services import detection, sync, training

    s = get(schedule_id)
    r = get_run(run_id)
    r.status = "running"
    _write_run(r)
    prev = next((x for x in list_runs(s.id, limit=20) if x.status == "done" and x.run_id != run_id), None)
    warnings: list[str] = []
    try:
        conn = connectors.get(s.connector_id)
        # 1 data
        if s.pipeline.sync:
            out = sync.run_sync(jobs.ScopedContext(ctx, 0, 35, "sync:"), conn.id)
            ds_id = out["dataset_id"]
            warnings += out["warnings"]
            r.data_through = out["synced_through"]
        else:
            ds_id = sync.latest_dataset_id(conn.id)
            if not ds_id:
                raise connectors.ConnectorError(f"There is no snapshot of {conn.name} yet; switch on syncing for this schedule.", "no_data")
            meta = storage.get_dataset_meta(ds_id)
            r.data_through = meta.date_end if meta else None
        r.dataset_id = ds_id
        ctx.check_cancelled()
        # 2 model
        p = s.pipeline
        model_id: str | None = None
        if p.model_policy == "retrain":
            due = True
            if p.train.min_interval_days and s.last_retrain_at and s.last_model_id and storage.get_model_summary(s.last_model_id):
                due = _utcnow() - (_parse(s.last_retrain_at) or _utcnow()) >= timedelta(days=p.train.min_interval_days)
            if due:
                req = TrainRequest(
                    dataset_id=ds_id, models=p.train.models, run_name=f"Scheduled · {s.name}", train_sample_size=p.train.train_sample_size,
                    alert_rate=p.train.alert_rate, activate_best=p.train.activate_retrained,
                )
                _, selections, tj_id, run_name = training.prepare(req)
                res = training._run_job(jobs.ScopedContext(ctx, 35, 70, "train:"), req, tj_id, selections, run_name)
                model_id = res["best_model_id"]
                r.retrained = True
                _patch(s.id, last_retrain_at=_iso(_utcnow()), last_model_id=model_id)
            else:
                model_id = s.last_model_id
        elif p.model_policy == "fixed":
            model_id = p.model_id
        else:
            model_id = storage.get_active_model_id()
        if not model_id or storage.get_model_summary(model_id) is None:
            raise LookupError("No model to score with: train one first, or set this schedule to retrain." if p.model_policy == "active" else f"Model {model_id} no longer exists; pick another on the schedule.")
        r.model_id = model_id
        # 3 detect
        det = detection.run_inline(jobs.ScopedContext(ctx, 70, 95, "detect:"), ds_id, model_id)
        r.detection_run_id = det["run_id"]
        r.alerts = int(det["incidents"])
        r.value_at_risk_gbp = float(det["value_at_risk_gbp"])
        # 4 new alerts and proposals
        ctx.step("propose", "Checking new alerts")
        new = _new_alerts(det["run_id"], prev.data_through if prev else None, r.data_through)
        r.new_alerts = len(new)
        r.new_critical = int((new["severity"] == "critical").sum()) if len(new) else 0
        if p.auto_tasks.enabled and len(new):
            r.proposal_id = _propose_tasks(s, det["run_id"], new, warnings)
        ctx.progress(100)
        r.status = "done"
        r.warnings = warnings
        return {"schedule_run_id": r.run_id, "dataset_id": ds_id, "model_id": model_id, "run_id": det["run_id"], "new_alerts": r.new_alerts, "proposal_id": r.proposal_id}
    except jobs.JobCancelled:
        r.status = "cancelled"
        r.error = "Cancelled."
        raise
    except connectors.ConnectorError as exc:
        r.status, r.error, r.error_kind, r.sop_id = "failed", str(exc), exc.kind, FEED_SOP
        raise
    except (LookupError, ValueError) as exc:
        r.status, r.error, r.error_kind, r.sop_id = "failed", str(exc), "model", FEED_SOP
        raise
    except Exception as exc:
        traceback.print_exc()
        r.status, r.error, r.error_kind, r.sop_id = "failed", f"{type(exc).__name__}: {exc}", "internal", FEED_SOP
        raise
    finally:
        r.finished_at = storage.now_iso()
        r.warnings = warnings
        _write_run(r)


def _new_alerts(run_id: str, prev_through: str | None, data_through: str | None):
    """Alerts that reach into days the previous scheduled run had not seen (first run: the last 7 days)."""
    from app.services import vendor_tasks

    inc = storage.load_run(run_id).incidents
    if not len(inc):
        return inc
    if prev_through:
        cut = prev_through
    elif data_through:
        cut = (datetime.fromisoformat(data_through) - timedelta(days=7)).date().isoformat()
    else:
        cut = "0000"
    new = inc[inc["end_date"].astype(str) > cut]
    raised = {t.alert_key for t in vendor_tasks.list_tasks(limit=100_000)}
    return new[~new["alert_key"].isin(raised)] if raised else new


def _propose_tasks(s: Schedule, run_id: str, new: Any, warnings: list[str]) -> str | None:
    from app.assistant import proposals
    from app.services import sops

    a = s.pipeline.auto_tasks
    pick = new[new["severity"].isin(a.severities) & (new["value_at_risk_gbp"] >= a.min_value_gbp)]
    pick = pick.sort_values("value_at_risk_gbp", ascending=False).head(a.max_tasks)
    if not len(pick):
        return None
    tasks = []
    for row in pick.to_dict("records"):
        sop_id = sops.sop_id_for_type(row["likely_type"])
        step = next((st for st in (sops.load().get(sop_id).steps if sop_id in sops.load() else []) if st.vendor_task), None)
        tasks.append({"alert_id": row["alert_id"], "type": (step.vendor_task or {}).get("type") if step else None, "sop_id": sop_id, "sop_step": step.id if step else None})
    try:
        p = proposals.create(
            f"scheduler:{s.id}", "vendor_task", {"connector_id": s.connector_id, "run_id": run_id, "tasks": tasks},
            ttl_s=config.SCHEDULER_PROPOSAL_TTL_S, source="scheduler",
        )
        return p.proposal_id
    except Exception as exc:  # noqa: BLE001 - a proposal problem must not fail the run
        warnings.append(f"Could not propose vendor tasks: {exc}")
        return None


# ---------------------------------------------------------------- the engine
def tick(now: datetime | None = None) -> list[ScheduleRun]:
    """Start every enabled schedule that is due at `now` (UTC). Called by the engine thread and by tests."""
    global _last_tick
    now = now or _utcnow()
    started: list[ScheduleRun] = []
    for s in list_all():
        if not s.enabled:
            continue
        due = _parse(s.next_run_at)
        if due is None:
            _patch(s.id, next_run_at=_iso(next_run(s, now)))
            continue
        if now < due:
            continue
        late = (now - due).total_seconds() > max(3 * config.SCHEDULER_TICK_S, 120)
        trigger = "catch_up" if late else "timer"
        if late and s.catch_up == "skip":
            ts = storage.now_iso()
            started.append(_write_run(ScheduleRun(run_id=storage.new_id("srun"), schedule_id=s.id, schedule_name=s.name, trigger="catch_up", status="skipped", started_at=ts, finished_at=ts,
                                                  error=f"Missed the {due.isoformat()} run while Sentinel was not running (catch-up is off).", error_kind="missed")))
        else:
            try:
                r, _ = launch(s, trigger)
                started.append(r)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                ts = storage.now_iso()
                started.append(_write_run(ScheduleRun(run_id=storage.new_id("srun"), schedule_id=s.id, schedule_name=s.name, trigger=trigger, status="failed", started_at=ts, finished_at=ts,  # type: ignore[arg-type]
                                                      error=str(exc), error_kind="internal", sop_id=FEED_SOP)))
        _patch(s.id, next_run_at=_iso(next_run(s, now)))
    _last_tick = _iso(now)
    return started


def recover() -> int:
    """At startup: runs left queued/running by a previous process cannot finish (jobs live in memory)."""
    n = 0
    for r in list(_runs().values()):
        if r.status in ("queued", "running") and (r.job_id is None or jobs.get(r.job_id) is None):
            r.status, r.finished_at, r.error, r.error_kind, r.sop_id = "failed", storage.now_iso(), "Sentinel restarted while this run was in progress.", "internal", FEED_SOP
            _write_run(r)
            n += 1
    return n


def _loop() -> None:
    while not _stop.wait(config.SCHEDULER_TICK_S):
        try:
            tick()
        except Exception:  # noqa: BLE001
            traceback.print_exc()


def start() -> None:
    global _thread
    n = recover()
    if n:
        print(f"[scheduler] marked {n} interrupted run(s) as failed")
    _stop.clear()
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_loop, name="sentinel-scheduler", daemon=True)
        _thread.start()
    enabled = [s for s in list_all() if s.enabled]
    print(f"[scheduler] running: {len(enabled)} enabled schedule(s), tick {config.SCHEDULER_TICK_S}s")
    try:
        tick()  # catch up straight away rather than after the first interval
    except Exception:  # noqa: BLE001
        traceback.print_exc()


def stop() -> None:
    _stop.set()


def status() -> SchedulerStatus:
    items = list_all()
    return SchedulerStatus(running=_thread is not None and _thread.is_alive() and not _stop.is_set(), last_tick=_last_tick, tick_seconds=config.SCHEDULER_TICK_S, schedules=len(items), enabled=sum(s.enabled for s in items))

