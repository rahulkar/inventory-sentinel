"""Job proposals: the assistant suggests a job, the user confirms it in the UI, then it runs through the normal job queue."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app import config
from app.schemas import ConfigureRequest, DetectRequest, GenerateRequest, ModelSelection, RetrainRequest, TrainRequest
from app.services import jobs, registry, storage, training, triage

ProposalKind = Literal["generate", "configure", "train", "detect", "retrain_feedback", "export_dataset", "export_onnx", "activate_model"]
KINDS = ["generate", "configure", "train", "detect", "retrain_feedback", "export_dataset", "export_onnx", "activate_model"]
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
    items = sorted(_store.values(), key=lambda p: p.created_at)[-200:]
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
            if now - created > config.ASSISTANT_PROPOSAL_TTL_S:
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


# ---------------------------------------------------------------- validation
def _dataset(dataset_id: str | None):
    if not dataset_id:
        ds = storage.list_datasets()
        if not ds:
            raise ProposalError("There is no dataset yet. Generate or import one first.")
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
    if kind == "generate":
        req = GenerateRequest(**{k: v for k, v in params.items() if k in GenerateRequest.model_fields})
        n = req.n_stores * req.n_skus * req.n_days
        if n < config.MIN_ROWS or n > config.MAX_ROWS:
            raise ProposalError(f"{n:,} rows is outside the allowed {config.MIN_ROWS:,}-{config.MAX_ROWS:,}. Change stores, SKUs or days.")
        est = n / 1e6 * config.TIMING["generate_s_per_1m"] + 3
        summary = (
            f"{req.n_stores} stores x {req.n_skus} SKUs x {req.n_days} days with injected theft, scan fraud, miscounts, receiving and data-entry errors "
            f"(anomaly level x{req.anomaly_multiplier}, loss-prevention coverage {req.lp_coverage:.0%}). Takes {_fmt_dur(est)}."
        )
        return req.model_dump(), f"Generate {n:,} rows of inventory data", summary, est, warnings
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
    raise ProposalError(f"Unsupported kind '{kind}'.")


def create(session_id: str, kind: str, params: dict[str, Any] | None) -> Proposal:
    try:
        norm, title, summary, est, warnings = _normalise(kind, params or {})
    except ValidationError as exc:
        raise ProposalError("; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())) from exc
    except (LookupError, ValueError) as exc:
        if isinstance(exc, ProposalError):
            raise
        raise ProposalError(str(exc)) from exc
    if jobs.is_busy():
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
        if p.kind == "generate":
            from app.routers.datasets import generate

            job = generate(GenerateRequest(**p.params))
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
