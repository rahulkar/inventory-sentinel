"""Proposals: the assistant (or a scheduled run) suggests an action, a person confirms it in the UI, then it runs.

Jobs (sync, train, detect, ...) go through the normal job queue. Schedule changes and vendor tasks are applied
directly on confirmation. Vendor tasks proposed by a scheduled run wait up to 72 hours for approval."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app import config
from app.schemas import ConfigureRequest, DetectRequest, ModelSelection, RetrainRequest, ScheduleIn, TrainRequest, VendorTaskDraft
from app.services import connectors, jobs, registry, storage, training, triage

ProposalKind = Literal[
    "sync", "configure", "train", "detect", "retrain_feedback", "export_dataset", "export_onnx", "activate_model",
    "create_schedule", "update_schedule", "run_schedule", "vendor_task",
]
KINDS = [
    "sync", "configure", "train", "detect", "retrain_feedback", "export_dataset", "export_onnx", "activate_model",
    "create_schedule", "update_schedule", "run_schedule", "vendor_task",
]
JOB_KINDS = {"sync", "configure", "train", "detect", "retrain_feedback", "export_dataset", "export_onnx", "run_schedule"}  # the rest apply at once
RECOMMENDED_MODELS = list(config.RECOMMENDED_MODELS)


class Proposal(BaseModel):
    proposal_id: str
    session_id: str
    kind: ProposalKind
    title: str
    summary: str
    params: dict[str, Any]
    estimate_seconds: float | None = None
    warnings: list[str] = []
    status: Literal["pending", "confirmed", "cancelled", "expired", "failed"] = "pending"
    job_id: str | None = None
    created_at: str
    decided_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    ttl_s: int | None = None  # None = the chat default (ASSISTANT_PROPOSAL_TTL_S)
    source: Literal["chat", "scheduler", "mcp"] = "chat"


class ProposalError(ValueError):
    """User-facing validation error."""


_lock = threading.RLock()
_store: dict[str, Proposal] = {}
_loaded = False


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    path = config.ASSISTANT_PROPOSALS_PATH
    if not path.exists():
        return
    try:
        for item in json.loads(path.read_text(encoding="utf-8")):
            try:
                p = Proposal(**item)
                _store[p.proposal_id] = p
            except ValidationError:
                continue
    except ValueError:
        pass


def _save() -> None:
    config.ensure_dirs()
    pending = [p for p in _store.values() if p.status == "pending"]
    others = sorted((p for p in _store.values() if p.status != "pending"), key=lambda p: p.created_at)[-200:]
    items = sorted(pending + others, key=lambda p: p.created_at)
    storage.atomic_write_text(config.ASSISTANT_PROPOSALS_PATH, json.dumps([p.model_dump() for p in items], indent=1))


def load() -> None:
    with _lock:
        _load()


def _expire() -> None:
    now = time.time()
    for p in _store.values():
        if p.status == "pending":
            try:
                created = datetime.fromisoformat(p.created_at).timestamp()
            except ValueError:
                continue
            if now - created > (p.ttl_s or config.ASSISTANT_PROPOSAL_TTL_S):
                p.status = "expired"


def get(proposal_id: str) -> Proposal | None:
    with _lock:
        _load()
        _expire()
        p = _store.get(proposal_id)
        return p.model_copy(deep=True) if p else None


def list_for_session(session_id: str | None, limit: int = 20) -> list[Proposal]:
    with _lock:
        _load()
        _expire()
        items = [p for p in _store.values() if session_id is None or p.session_id == session_id]
    items.sort(key=lambda p: p.created_at, reverse=True)
    return [p.model_copy(deep=True) for p in items[:limit]]


def list_pending(source: str | None = None, limit: int = 50) -> list[Proposal]:
    """Proposals still waiting for a person (e.g. vendor tasks from overnight scheduled runs)."""
    with _lock:
        _load()
        _expire()
        items = [p for p in _store.values() if p.status == "pending" and (source is None or p.source == source)]
    items.sort(key=lambda p: p.created_at, reverse=True)
    return [p.model_copy(deep=True) for p in items[:limit]]


# ---------------------------------------------------------------- validation
def _dataset(dataset_id: str | None):
    if not dataset_id:
        ds = storage.list_datasets()
        if not ds:
            raise ProposalError("There is no dataset yet. Sync a vendor connector (Data page) or import a CSV first.")
        return ds[0]
    meta = storage.get_dataset_meta(dataset_id)
    if meta is None:
        raise ProposalError(f"Dataset '{dataset_id}' was not found.")
    return meta


def _model(model_id: str | None):
    mid = model_id or storage.get_active_model_id()
    if not mid:
        raise ProposalError("No model is in use yet; train one first or name a model id.")
    meta = storage.get_model(mid)
    if meta is None:
        raise ProposalError(f"Model '{mid}' was not found.")
    return meta


def _fmt_dur(seconds: float | None) -> str:
    if seconds is None:
        return "a moment"
    s = max(0, round(seconds))
    if s < 10:
        return "a few seconds"
    if s < 60:
        return f"about {round(s / 5) * 5} seconds"
    return f"about {max(1, round(s / 60))} minute{'s' if round(s / 60) != 1 else ''}"


def _normalise(kind: str, params: dict[str, Any]) -> tuple[dict[str, Any], str, str, float | None, list[str]]:
    """Validate and complete parameters; returns (params, title, summary, estimate seconds, warnings)."""
    warnings: list[str] = []
    if kind not in KINDS:
        raise ProposalError(f"Unknown job kind '{kind}'. Use one of: {', '.join(KINDS)}.")
    if kind == "sync":
        try:
            c = connectors.get(params.get("connector_id"))
        except LookupError as exc:
            raise ProposalError(str(exc)) from exc
        if not c.enabled:
            raise ProposalError(f"{c.name} is switched off; enable it on the Data page first.")
        full = bool(params.get("full", False))
        last = c.last_sync
        est = (last.seconds if last and last.seconds and not full else None) or config.TIMING["sync_s_per_1m"] * 1.2 + 10
        since = f"last synced through {last.synced_through}" if last and last.synced_through else "first sync: pulls the whole window"
        summary = (
            f"Pull {'all' if full else 'new'} trading days from {c.name} over MCP ({since}), rebuild a {c.window_days}-day snapshot and keep the newest "
            f"{c.retention}. Takes {_fmt_dur(est)}."
        )
        return {"connector_id": c.id, "full": full}, f"Sync {c.name}", summary, est, warnings
    if kind == "configure":
        ds = _dataset(params.get("dataset_id"))
        if ds.kind != "upload":
            raise ProposalError("Only imported datasets can be re-mapped.")
        cmap = dict(params.get("column_map") or {})
        return {"dataset_id": ds.id, "column_map": cmap, "name": params.get("name")}, f"Re-process {ds.name}", f"Re-map columns {cmap or '(auto-detect again)'} and rebuild features.", 10 + ds.n_rows / 1e6 * 5, warnings
    if kind == "train":
        ds = _dataset(params.get("dataset_id"))
        keys = params.get("models") or RECOMMENDED_MODELS
        keys = [k if isinstance(k, str) else k.get("key") for k in keys]
        bad = [k for k in keys if k not in registry.REGISTRY]
        if bad:
            raise ProposalError(f"Unknown method(s): {', '.join(bad)}. Choose from {', '.join(registry.REGISTRY)}.")
        unavailable = [registry.REGISTRY[k].label for k in keys if not registry.REGISTRY[k].available]
        if unavailable:
            raise ProposalError(f"Not available on this machine: {', '.join(unavailable)}.")
        quick = bool(params.get("quick", False))
        sample = int(params.get("train_sample_size") or (config.QUICK_TRAIN_SAMPLE if quick else config.DEFAULT_TRAIN_SAMPLE))
        alert_rate = float(params.get("alert_rate") or config.DEFAULT_ALERT_RATE)
        req = TrainRequest(dataset_id=ds.id, models=[ModelSelection(key=k) for k in keys], run_name=params.get("run_name"), train_sample_size=sample, alert_rate=alert_rate)
        est = training.estimate_seconds(keys, min(sample, ds.n_rows), config.EVAL_NEGATIVES)
        labels = ", ".join(registry.REGISTRY[k].label for k in keys)
        for k in keys:
            if "fallback" in registry.REGISTRY[k].engine:
                warnings.append(f"{registry.REGISTRY[k].label} will use the built-in numpy engine on this machine.")
        summary = f"Fit on a {sample:,}-row sample of the history window, alert rate {alert_rate:.1%}, judged on the last {config.TEST_WINDOW_SHARE:.0%} of days. Takes {_fmt_dur(est)}."
        return req.model_dump(), f"Train {labels} on {ds.name}", summary, est, warnings
    if kind == "detect":
        ds = _dataset(params.get("dataset_id"))
        m = _model(params.get("model_id"))
        per_1m = m.metrics.score_seconds_per_1m or 20.0
        est = ds.n_rows / 1e6 * (per_1m + config.TIMING["detect_overhead_s_per_1m"]) + 5
        if est > 180:
            warnings.append(f"Scoring with {m.label} takes {_fmt_dur(est)} at this size.")
        summary = f"Score all {ds.n_rows:,} store-SKU-days, group flagged days into alerts and build the dashboard. Takes {_fmt_dur(est)}."
        return {"dataset_id": ds.id, "model_id": m.model_id}, f"Detect anomalies in {ds.name} with {m.label}", summary, est, warnings
    if kind == "retrain_feedback":
        m = _model(params.get("model_id"))
        if m.key == "reranker":
            if not m.parent_model_id:
                raise ProposalError("Pick an unsupervised model to sit under the re-ranker.")
            m = _model(m.parent_model_id)
        summ = triage.summary(m.dataset_id, None)
        if not summ.can_retrain:
            raise ProposalError(summ.retrain_reason or "Not enough team feedback yet.")
        alpha = float(params.get("alpha", 0.4))
        summary = f"Train a feedback re-ranker on {summ.reviewed} reviewed alerts ({summ.true_alerts} real, {summ.false_alarms} false alarms) plus loss-prevention flags, then compare it with {m.label} on days nobody reviewed."
        return {"model_id": m.model_id, "alpha": alpha}, f"Retrain {m.label} with {summ.reviewed} team decisions", summary, 40.0, warnings
    if kind == "export_dataset":
        ds = _dataset(params.get("dataset_id"))
        est = ds.n_rows / 1e6 * config.TIMING["export_s_per_1m"] + 3
        summary = f"daily.csv ({ds.n_rows:,} rows) plus stores, SKUs, loss-prevention flags{' and the answer key' if ds.has_truth else ''}. Takes {_fmt_dur(est)}."
        return {"dataset_id": ds.id}, f"Export {ds.name} as a ZIP", summary, est, warnings
    if kind == "export_onnx":
        m = _model(params.get("model_id"))
        if not m.onnx_ok:
            raise ProposalError(m.onnx_reason or f"{m.label} cannot be exported to ONNX.")
        return {"model_id": m.model_id}, f"Export {m.label} to ONNX", "Build an ONNX graph and check it ranks 2,000 sample days exactly like the Python model.", 15.0, warnings
    if kind == "activate_model":
        m = _model(params.get("model_id"))
        return {"model_id": m.model_id}, f"Use {m.label} for new detection runs", f"{m.name}: average precision {m.metrics.average_precision}.", None, warnings
    if kind in ("create_schedule", "update_schedule"):
        from app.services import scheduler

        base: dict[str, Any] | None = None
        sched = None
        if kind == "update_schedule":
            if not params.get("schedule_id"):
                raise ProposalError("Name the schedule to change (schedule_id).")
            sched = scheduler.get(params["schedule_id"])
            base = sched.model_dump(include=set(ScheduleIn.model_fields))
        body = scheduler.validate(_schedule_body(params, base))
        desc = scheduler.describe(body) + "."
        if body.pipeline.model_policy == "retrain" and body.pipeline.train.activate_retrained:
            warnings.append("Each retrain will replace the model in use.")
        if body.pipeline.auto_tasks.enabled:
            warnings.append("Vendor tasks from scheduled runs are only proposed; someone approves them within 72 hours.")
        out = body.model_dump()
        if sched is not None:
            return {"schedule_id": sched.id, "schedule": out}, f"Change schedule '{sched.name}'", desc, None, warnings
        return {"schedule": out}, f"Schedule '{body.name}'", desc, None, warnings
    if kind == "run_schedule":
        from app.services import scheduler

        if not params.get("schedule_id"):
            items = scheduler.list_all()
            if len(items) != 1:
                raise ProposalError("Name the schedule to run (schedule_id)." if items else "There are no schedules yet.")
            params = {**params, "schedule_id": items[0].id}
        sched = scheduler.get(params["schedule_id"])
        return {"schedule_id": sched.id}, f"Run '{sched.name}' now", scheduler.describe(sched) + ".", scheduler._estimate(sched), warnings
    if kind == "vendor_task":
        return _vendor_task(params, warnings)
    raise ProposalError(f"Unsupported kind '{kind}'.")


DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _schedule_body(params: dict[str, Any], base: dict[str, Any] | None) -> ScheduleIn:
    """Accept a full ScheduleIn under "schedule" or flat shortcuts (at, days, every_hours, models, model_policy, ...)."""
    body: dict[str, Any] = dict(base or {})
    nested = params.get("schedule") or {}
    body.update({k: v for k, v in nested.items() if k in ScheduleIn.model_fields})
    for k in ("name", "enabled", "connector_id", "timezone", "catch_up"):
        if params.get(k) is not None:
            body[k] = params[k]
    if not body.get("connector_id"):
        try:
            body["connector_id"] = connectors.get(None).id
        except LookupError as exc:
            raise ProposalError(str(exc)) from exc
    freq = dict(body.get("frequency") or {})
    if params.get("every_hours"):
        freq.update(kind="interval", every_hours=int(params["every_hours"]))
    if params.get("at"):
        freq["at"] = str(params["at"])
        if freq.get("kind") in (None, "interval"):
            freq["kind"] = "daily"
    if params.get("days") is not None:
        try:
            freq["days"] = sorted({d if isinstance(d, int) else DAY_NAMES.index(str(d).lower()[:3]) for d in params["days"]})
        except ValueError as exc:
            raise ProposalError("Days are 0-6 (Monday = 0) or names like 'mon'.") from exc
        if freq.get("kind") != "interval":
            freq["kind"] = "weekly" if len(freq["days"]) < 7 else "daily"
    if params.get("frequency_kind"):
        freq["kind"] = params["frequency_kind"]
    body["frequency"] = freq
    pipe = dict(body.get("pipeline") or {})
    if params.get("sync") is not None:
        pipe["sync"] = bool(params["sync"])
    models = params.get("models") or params.get("algorithms")
    if models:
        train = dict(pipe.get("train") or {})
        train["models"] = [{"key": m} if isinstance(m, str) else m for m in models]
        pipe["train"] = train
        if not params.get("model_policy"):
            pipe["model_policy"] = "retrain"
    for k in ("model_policy", "model_id"):
        if params.get(k):
            pipe[k] = params[k]
    if pipe.get("model_policy") == "retrain":
        train = dict(pipe.get("train") or {})
        for k in ("train_sample_size", "alert_rate", "activate_retrained", "min_interval_days"):
            if params.get(k) is not None:
                train[k] = params[k]
        pipe["train"] = train
    at = params.get("auto_tasks")
    if at is not None or any(params.get(k) is not None for k in ("severities", "min_value_gbp", "max_tasks")):
        auto = dict(pipe.get("auto_tasks") or {})
        if isinstance(at, dict):
            auto.update(at)
        elif at is not None:
            auto["enabled"] = bool(at)
        for k in ("severities", "min_value_gbp", "max_tasks"):
            if params.get(k) is not None:
                auto[k] = params[k]
        pipe["auto_tasks"] = auto
    body["pipeline"] = pipe
    if not body.get("name"):
        body["name"] = f"Every {freq.get('every_hours')} hours" if freq.get("kind") == "interval" else f"Daily scan at {freq.get('at', '06:00')}"
    return ScheduleIn(**body)


def _vendor_task(params: dict[str, Any], warnings: list[str]) -> tuple[dict[str, Any], str, str, float | None, list[str]]:
    from app.services import detection, sops, vendor_tasks

    run_id = params.get("run_id")
    if not run_id:
        raise ProposalError("Name the detection run the alerts come from (run_id).")
    items = params.get("tasks") or ([{"alert_id": params["alert_id"], "type": params.get("type")}] if params.get("alert_id") else [])
    if not items:
        raise ProposalError("List at least one alert to raise a task for.")
    try:
        conn = connectors.get(params["connector_id"]) if params.get("connector_id") else vendor_tasks.connector_for_run(run_id)
    except (LookupError, ValueError) as exc:
        raise ProposalError(str(exc)) from exc
    accepted = (conn.capabilities or {}).get("task_types") or []
    out, lines = [], []
    for it in items[:50]:
        if isinstance(it, str):
            it = {"alert_id": it}
        a = detection.get_alert(run_id, it["alert_id"])
        sop_id = it.get("sop_id") or sops.sop_id_for_type(a.likely_type)
        step = sops.step(sop_id, it["sop_step"]) if sop_id and it.get("sop_step") else None
        filled = vendor_tasks.draft_for_alert(run_id, a.alert_id, it.get("type"), step)
        if accepted and filled["type"] not in accepted:
            warnings.append(f"{conn.name} does not take '{filled['type']}' tasks; skipped {a.alert_id}.")
            continue
        if any(t.type == filled["type"] for t in vendor_tasks.for_alert(a.alert_key)):
            warnings.append(f"A {filled['type']} task already exists for {a.sku_name} at {a.store_name}; skipped.")
            continue
        out.append({"alert_id": a.alert_id, "type": filled["type"], "priority": it.get("priority") or filled["priority"], "sop_id": sop_id, "sop_step": it.get("sop_step"), "note": it.get("note"), "title": filled["title"]})
        lines.append(f"{filled['title']} ({a.severity}, £{a.value_at_risk_gbp:,.0f})")
    if not out:
        raise ProposalError("Nothing to raise: " + (" ".join(warnings) or "no matching alerts."))
    n = len(out)
    plural = "s" if n != 1 else ""
    summary = f"Raise {n} task{plural} in {conn.name}'s back-office for store teams: " + "; ".join(lines[:5]) + (f"; and {n - 5} more" if n > 5 else "") + "."
    return {"connector_id": conn.id, "run_id": run_id, "tasks": out}, f"Raise {n} vendor task{plural} in {conn.name}", summary, None, warnings


def create(session_id: str, kind: str, params: dict[str, Any] | None, ttl_s: int | None = None, source: str | None = None) -> Proposal:
    try:
        norm, title, summary, est, warnings = _normalise(kind, params or {})
    except ValidationError as exc:
        raise ProposalError("; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())) from exc
    except (LookupError, ValueError) as exc:
        if isinstance(exc, ProposalError):
            raise
        raise ProposalError(str(exc)) from exc
    if jobs.is_busy() and kind in JOB_KINDS:
        warnings.append("Another job is running; this one will queue behind it.")
    p = Proposal(
        proposal_id=storage.new_id("p"),
        session_id=session_id or "mcp",
        kind=kind,  # type: ignore[arg-type]
        title=title,
        summary=summary,
        params=norm,
        estimate_seconds=est,
        warnings=warnings,
        created_at=storage.now_iso(),
        ttl_s=ttl_s,
        source=source or ("mcp" if (session_id or "mcp") == "mcp" else "chat"),  # type: ignore[arg-type]
    )
    with _lock:
        _load()
        _store[p.proposal_id] = p
        _save()
    return p.model_copy(deep=True)


def cancel(proposal_id: str) -> Proposal:
    with _lock:
        _load()
        p = _store.get(proposal_id)
        if p is None:
            raise LookupError("Proposal not found.")
        if p.status == "pending":
            p.status = "cancelled"
            p.decided_at = storage.now_iso()
            _save()
        return p.model_copy(deep=True)


def execute(proposal_id: str) -> dict[str, Any]:
    """Run a pending proposal through the existing services. Returns {proposal, job, result}."""
    with _lock:
        _load()
        _expire()
        p = _store.get(proposal_id)
        if p is None:
            raise LookupError("Proposal not found.")
        if p.status != "pending":
            raise ProposalError(f"This proposal is {p.status}, it cannot be confirmed again.")
        p.status = "confirmed"
        p.decided_at = storage.now_iso()
    job = None
    result: dict[str, Any] | None = None
    try:
        if p.kind == "sync":
            from app.services import sync

            job = sync.start_job(p.params["connector_id"], bool(p.params.get("full")))
        elif p.kind in ("create_schedule", "update_schedule"):
            from app.services import scheduler

            body = ScheduleIn(**p.params["schedule"])
            sched = scheduler.update(p.params["schedule_id"], body) if p.kind == "update_schedule" else scheduler.create(body)
            result = {"schedule_id": sched.id, "name": sched.name, "next_run_at": sched.next_run_at}
        elif p.kind == "run_schedule":
            from app.services import scheduler

            run, job = scheduler.run_now(p.params["schedule_id"])
            result = {"schedule_run_id": run.run_id, "status": run.status, "error": run.error}
        elif p.kind == "vendor_task":
            from app.services import vendor_tasks

            drafts = [VendorTaskDraft(run_id=p.params["run_id"], **{k: v for k, v in t.items() if k in VendorTaskDraft.model_fields and k != "run_id"}) for t in p.params["tasks"]]
            result = vendor_tasks.create(drafts, source="scheduler" if p.source == "scheduler" else "proposal", connector_id=p.params.get("connector_id"))
            if not result["created"] and not result["existing"]:
                raise RuntimeError("; ".join(f["error"] for f in result["failed"]) or "No task was created.")
        elif p.kind == "configure":
            from app.routers.datasets import configure

            params = dict(p.params)
            ds_id = params.pop("dataset_id")
            job = configure(ds_id, ConfigureRequest(**params))
        elif p.kind == "train":
            job = training.start_job(TrainRequest(**p.params))
        elif p.kind == "detect":
            from app.services import detection

            job = detection.start_job(DetectRequest(**p.params))
        elif p.kind == "retrain_feedback":
            from app.services import reranker

            job = reranker.start_job(p.params["model_id"], RetrainRequest(alpha=p.params.get("alpha", 0.4)))
        elif p.kind == "export_dataset":
            from app.services import exporter

            job = exporter.start_export_job(p.params["dataset_id"])
        elif p.kind == "export_onnx":
            from app.services import model_export

            job = model_export.start_onnx_job(p.params["model_id"])
        elif p.kind == "activate_model":
            storage.set_active_model(p.params["model_id"])
            result = {"active_model_id": p.params["model_id"]}
    except Exception as exc:  # noqa: BLE001
        detail = getattr(exc, "detail", None) or str(exc)
        with _lock:
            p.status = "failed"
            p.error = str(detail)
            _save()
        return {"proposal": p.model_copy(deep=True), "job": None, "result": None}
    with _lock:
        p.job_id = job.job_id if job else None
        p.result = result
        _save()
        snap = p.model_copy(deep=True)
    return {"proposal": snap, "job": job, "result": result}
