"""Training jobs: fit detectors on the history window, set alert thresholds, evaluate on the held-out window."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

import numpy as np

from app import config
from app.schemas import Experiment, ImportanceItem, Job, Metrics, ModelMeta, ModelResult, ModelSummary, PRPoint, Thresholds, TrainJob, TrainRequest
from app.services import calibration, explain, jobs, registry, storage
from app.services import features as F
from app.services.detectors import pipeline_score

_train_jobs: OrderedDict[str, TrainJob] = OrderedDict()
_tj_lock = threading.Lock()

QUANTILE_LEVELS = np.unique(np.r_[np.linspace(0, 0.99, 100), 1 - np.geomspace(0.01, 1e-5, 160), 1.0])


# ---------------------------------------------------------------- helpers shared with detection / feedback
def feature_matrix(ds: storage.Dataset, rows: np.ndarray | slice) -> np.ndarray:
    return F.matrix(ds.features, F.FEATURES, rows)


def percentile_of(meta: ModelMeta, scores: np.ndarray) -> np.ndarray:
    levels = np.asarray(meta.quantile_levels) if meta.quantile_levels else np.linspace(0, 1, len(meta.score_quantiles))
    return np.interp(scores, np.asarray(meta.score_quantiles), levels, left=0.0, right=1.0)


def score_chunked(pipe: Any, ds: storage.Dataset, rows: np.ndarray | None = None, chunk: int = config.SCORE_CHUNK_ROWS, on_progress: Callable[[float], None] | None = None, check: Callable[[], None] | None = None) -> np.ndarray:
    n = ds.meta.n_rows if rows is None else len(rows)
    out = np.empty(n, dtype=np.float32)
    for i in range(0, n, chunk):
        if check:
            check()
        sel = slice(i, min(n, i + chunk)) if rows is None else rows[i : i + chunk]
        out[i : i + chunk] = pipeline_score(pipe, feature_matrix(ds, sel))
        if on_progress:
            on_progress(min(1.0, (i + chunk) / n))
    return out


def thresholds_from(quantiles: np.ndarray, levels: np.ndarray, alert_rate: float) -> Thresholds:
    q = lambda lv: float(np.interp(lv, levels, quantiles))  # noqa: E731
    alert = q(1 - alert_rate)
    high = max(q(config.SEVERITY_QUANTILES["high"]), alert)
    crit = max(q(config.SEVERITY_QUANTILES["critical"]), high)
    return Thresholds(alert=alert, high=high, critical=crit)


class EvalSet:
    """Rows used to judge a detector, with weights so sampled negatives stand for all negatives."""

    def __init__(self, ds: storage.Dataset, rng: np.random.Generator, train_rows: np.ndarray, exclude_rows: np.ndarray | None = None) -> None:
        n = ds.meta.n_rows
        date_idx = np.asarray(ds.daily["date_idx"])
        test = date_idx >= ds.test_from_idx
        if exclude_rows is not None and len(exclude_rows):
            test[exclude_rows] = False
        self.lp_rows = np.zeros(0, dtype=np.int64)
        if ds.truth:
            tt = np.asarray(ds.truth["truth_type"])
            self.source = "ground_truth"
            pos = np.flatnonzero(test & (tt > 0))
            neg_all = np.flatnonzero(test & (tt == 0))
            lp = ds.lp_mask()
            self.lp_rows = np.flatnonzero(lp & (date_idx < ds.test_from_idx))
        elif len(ds.lp_flags):
            lp = ds.lp_mask()
            self.source = "lp_flags"
            keep = np.ones(n, dtype=bool)
            keep[train_rows] = False
            pos = np.flatnonzero(lp & keep)
            neg_all = np.flatnonzero(~lp & keep)
        else:
            self.source = "none"
            pos = np.zeros(0, dtype=np.int64)
            neg_all = np.flatnonzero(test)
        k = min(config.EVAL_NEGATIVES, len(neg_all))
        neg = np.sort(rng.choice(neg_all, size=k, replace=False)) if k else neg_all[:0]
        self.rows = np.r_[pos, neg].astype(np.int64)
        self.y = np.r_[np.ones(len(pos)), np.zeros(len(neg))]
        self.w = np.r_[np.ones(len(pos)), np.full(len(neg), len(neg_all) / max(k, 1))]
        order = np.argsort(self.rows)
        self.rows, self.y, self.w = self.rows[order], self.y[order], self.w[order]
        self.n_pos = int(len(pos))
        if ds.truth:
            self.type = np.asarray(ds.truth["truth_type"])[self.rows]
            self.incident = np.asarray(ds.truth["truth_incident"])[self.rows]
            cost = ds.skus["unit_cost"].to_numpy(dtype=np.float64)[np.asarray(ds.daily["sku_code"])[self.rows].astype(np.int64)]
            self.loss_value = np.asarray(ds.truth["truth_loss_units"])[self.rows].astype(np.float64) * cost
        else:
            self.type = self.incident = self.loss_value = None


def evaluate(es: EvalSet, scores: np.ndarray, thr: Thresholds, lp_scores: np.ndarray | None) -> Metrics:
    from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

    flag = scores >= thr.alert
    m = Metrics(label_source=es.source, n_eval_rows=int(len(es.rows)), n_eval_positive=es.n_pos)  # type: ignore[arg-type]
    m.alert_rate = round(float((es.w * flag).sum() / max(es.w.sum(), 1e-9)), 5)
    if es.source == "none" or es.n_pos == 0:
        return m
    m.average_precision = round(float(average_precision_score(es.y, scores, sample_weight=es.w)), 4)
    m.roc_auc = round(float(roc_auc_score(es.y, scores, sample_weight=es.w)), 4)
    order = np.argsort(-scores, kind="stable")
    cw = np.cumsum(es.w[order])
    top = order[: int(np.searchsorted(cw, config.PRECISION_AT_K)) + 1]
    m.precision_at_k = round(float((es.w[top] * es.y[top]).sum() / max(es.w[top].sum(), 1e-9)), 4)
    m.recall_at_threshold = round(float((flag & (es.y == 1)).sum() / max(es.n_pos, 1)), 4)
    m.precision_at_threshold = round(float((es.w * flag * es.y).sum() / max((es.w * flag).sum(), 1e-9)), 4)
    prec, rec, _ = precision_recall_curve(es.y, scores, sample_weight=es.w)
    pick = np.unique(np.linspace(0, len(rec) - 1, min(60, len(rec))).astype(int))
    m.pr_curve = [PRPoint(recall=round(float(rec[i]), 4), precision=round(float(prec[i]), 4)) for i in pick]
    if es.incident is not None:
        pos = es.y == 1
        inc_all = np.unique(es.incident[pos])
        inc_hit = np.unique(es.incident[pos & flag])
        m.incident_recall = round(len(inc_hit) / max(len(inc_all), 1), 4)
        tot = es.loss_value[pos].sum()
        m.value_captured_pct = round(float(es.loss_value[pos & flag].sum() / tot * 100), 2) if tot > 0 else None
        by = {}
        for t in range(1, len(config.ANOMALY_TYPES)):
            sel = pos & (es.type == t)
            if sel.any():
                ia = np.unique(es.incident[sel])
                ih = np.unique(es.incident[sel & flag])
                by[config.ANOMALY_TYPES[t]] = round(len(ih) / max(len(ia), 1), 3)
        m.detection_by_type = by
    if lp_scores is not None and len(lp_scores):
        m.lp_recall = round(float((lp_scores >= thr.alert).mean()), 4)
    return m


def importances(feat_rows: np.ndarray, base: dict[str, Any]) -> list[ImportanceItem]:
    glob = base.get("global", {})
    contrib = {}
    for j, f in enumerate(F.FEATURES):
        if f not in F.DETECT_FEATURES or f not in glob:
            continue
        med, mad, q99 = glob[f]
        spread = max(mad, abs(q99 - med) / 3.0, 0.05)
        contrib[f] = float(np.clip(np.abs(feat_rows[:, j] - med) / spread, 0, 20).mean()) if len(feat_rows) else 0.0
    tot = sum(contrib.values()) or 1.0
    items = [ImportanceItem(feature=f, importance=round(v / tot, 4)) for f, v in contrib.items()]
    return sorted(items, key=lambda i: -i.importance)


# ---------------------------------------------------------------- job bookkeeping
def _set(job_id: str, fn: Callable[[TrainJob], None]) -> TrainJob | None:
    with _tj_lock:
        tj = _train_jobs.get(job_id)
        if tj is not None:
            fn(tj)
            return tj.model_copy(deep=True)
    return None


def get_job(job_id: str) -> TrainJob | None:
    with _tj_lock:
        tj = _train_jobs.get(job_id)
        snap = tj.model_copy(deep=True) if tj else None
    if snap is None:
        return None
    j = jobs.get(job_id)
    if j and j.status in ("cancelled", "failed") and snap.status != "done":
        snap.status = j.status
        snap.error = snap.error or j.error
    return snap


def list_jobs() -> list[TrainJob]:
    with _tj_lock:
        return [tj.model_copy(deep=True) for tj in reversed(_train_jobs.values())]


def estimate_seconds(keys: list[str], n_train: int, n_eval: int) -> float:
    total = 5.0
    for k in keys:
        spec = registry.get_spec(k)
        total += spec.fit_seconds * n_train / 200_000 + spec.score_seconds_per_1m * (n_train + n_eval) / 1_000_000
    return round(total, 1)


def start_job(req: TrainRequest) -> Job:
    meta = storage.get_dataset_meta(req.dataset_id)
    if meta is None:
        raise LookupError("Dataset not found.")
    selections = []
    for sel in req.models:
        try:
            spec = registry.get_spec(sel.key)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        if not spec.available:
            raise RuntimeError(f"{spec.label} is not available on this machine: {spec.reason}")
        selections.append((spec, registry.coerce_params(spec, sel.params)))
    if not selections:
        raise ValueError("Choose at least one method.")
    job_id = storage.new_id("job")
    run_name = req.run_name or f"Run {time.strftime('%H:%M:%S')}"
    tj = TrainJob(
        job_id=job_id, status="queued", run_name=run_name, dataset_id=meta.id, dataset_name=meta.name, created_at=storage.now_iso(),
        results=[ModelResult(key=s.key, label=s.label, status="pending") for s, _ in selections],
        progress={"done": 0, "total": len(selections)}, train_sample_size=req.train_sample_size,
    )
    with _tj_lock:
        _train_jobs[job_id] = tj
        while len(_train_jobs) > config.JOBS_KEEP:
            _train_jobs.popitem(last=False)
    steps = [("load", "Loading features"), ("sample", "Sampling history and the evaluation window")]
    steps += [(f"model:{s.key}", f"Training {s.label}") for s, _ in selections]
    steps += [("finish", "Saving models")]
    n_train = min(req.train_sample_size, meta.n_rows)
    return jobs.submit(
        "train", f"Train {len(selections)} method{'s' if len(selections) > 1 else ''} on {meta.name}",
        lambda ctx: _run_job(ctx, req, job_id, selections, run_name),
        params=req.model_dump(), steps=steps, estimate_seconds=estimate_seconds([s.key for s, _ in selections], n_train, config.EVAL_NEGATIVES), job_id=job_id,
    )


def train_sample(ds: storage.Dataset, size: int, exclude_lp: bool, seed: int, extra_exclude: np.ndarray | None = None) -> np.ndarray:
    date_idx = np.asarray(ds.daily["date_idx"])
    ok = date_idx < ds.test_from_idx
    if exclude_lp:
        ok &= ~ds.lp_mask()
    if extra_exclude is not None and len(extra_exclude):
        ok[extra_exclude] = False
    cand = np.flatnonzero(ok)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(cand, size=min(size, len(cand)), replace=False))


def _run_job(ctx: jobs.JobContext, req: TrainRequest, job_id: str, selections: list[tuple[registry.ModelSpec, dict[str, Any]]], run_name: str) -> dict[str, Any]:
    _set(job_id, lambda t: setattr(t, "status", "running"))
    ctx.step("load", "Loading features")
    ds = storage.load_dataset(req.dataset_id)
    rng = np.random.default_rng(req.random_state)
    ctx.step("sample", "Sampling history and the evaluation window")
    tr = train_sample(ds, req.train_sample_size, req.exclude_lp_flagged, req.random_state)
    Xtr = feature_matrix(ds, tr)
    es = EvalSet(ds, rng, tr)
    Xev = feature_matrix(ds, es.rows)
    Xlp = feature_matrix(ds, es.lp_rows) if len(es.lp_rows) else None
    cats = np.asarray(ds.features["category"])[tr].astype(int)
    base = explain.baseline({f: Xtr[:, F.FEATURES.index(f)] for f in F.DETECT_FEATURES}, cats, ds.meta.categories)
    ctx.progress(8)
    results: list[ModelMeta] = []
    total = len(selections)
    for i, (spec, params) in enumerate(selections):
        ctx.check_cancelled()
        ctx.step(f"model:{spec.key}", f"Training {spec.label}")
        _set(job_id, lambda t, k=spec.key: [setattr(r, "status", "running") for r in t.results if r.key == k])
        t0 = time.time()
        try:
            pipe = spec.build(params, req.random_state, F.FEATURES, ds.meta.detect_features)
            pipe.fit(Xtr)
            fit_s = time.time() - t0
            s_tr = pipeline_score(pipe, Xtr)
            q = np.quantile(s_tr, QUANTILE_LEVELS)
            thr = thresholds_from(q, QUANTILE_LEVELS, req.alert_rate)
            t1 = time.time()
            s_ev = pipeline_score(pipe, Xev)
            per_1m = (time.time() - t1) / max(len(Xev), 1) * 1_000_000
            s_lp = pipeline_score(pipe, Xlp) if Xlp is not None else None
            metrics = evaluate(es, s_ev, thr, s_lp)
            metrics.fit_seconds = round(fit_s, 2)
            metrics.score_seconds_per_1m = round(per_1m, 1)
            metrics.n_train = int(len(tr))
            flagged = Xev[s_ev >= thr.alert]
            meta = ModelMeta(
                model_id=storage.new_id("m"), name=f"{spec.label} · {ds.meta.name[:40]} · {time.strftime('%H:%M')}", key=spec.key, label=spec.label,
                dataset_id=ds.meta.id, dataset_name=ds.meta.name, run_name=run_name, created_at=storage.now_iso(), metrics=metrics,
                engine=getattr(pipe.named_steps["model"], "engine_", "sklearn"), job_id=job_id, train_sample_size=int(len(tr)),
                params=params, feature_columns=list(F.FEATURES), input_features=list(ds.meta.detect_features) if spec.key != "zscore" else list(F.BASELINE_FEATURES),
                categories=ds.meta.categories, thresholds=thr, score_quantiles=[float(x) for x in q], quantile_levels=[float(x) for x in QUANTILE_LEVELS],
                importances=importances(flagged, base), feature_baseline=base, alert_rate=req.alert_rate, test_from_date=ds.meta.test_from_date,
            )
            pct = percentile_of(meta, s_ev)
            if es.source != "none" and es.n_pos:
                note = "From the synthetic answer key on the evaluation window." if es.source == "ground_truth" else "From loss-prevention flags: a lower bound, because most incidents were never flagged."
                meta.calibration = calibration.fit(pct, es.y, es.w, 1 - req.alert_rate, es.source, note)
            else:
                meta.calibration = calibration.prior(1 - req.alert_rate)
            fb = getattr(pipe.named_steps["model"], "fallback_reason_", None)
            if fb:
                meta.notes.append(f"Trained with the built-in numpy engine because scikit-learn's compiled module could not load ({fb[:120]}).")
            from app.services import model_export

            meta.onnx_ok, meta.onnx_reason = model_export.onnx_supported(meta, pipe)
            storage.save_model(meta, pipe)
            results.append(meta)
            _set(job_id, lambda t, k=spec.key, mm=meta: [r.__setattr__("status", "done") or r.__setattr__("model_id", mm.model_id) or r.__setattr__("metrics", mm.metrics) or r.__setattr__("seconds", round(time.time() - t0, 1)) for r in t.results if r.key == k])
        except jobs.JobCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - one failing method should not sink the run
            import traceback

            traceback.print_exc()
            ctx.warn(f"{spec.label} failed: {exc}")
            _set(job_id, lambda t, k=spec.key, e=str(exc): [r.__setattr__("status", "failed") or r.__setattr__("error", e[:300]) for r in t.results if r.key == k])
        _set(job_id, lambda t, d=i + 1: t.progress.__setitem__("done", d))
        ctx.progress(8 + 88 * (i + 1) / total)
    ctx.step("finish", "Saving models")
    if not results:
        raise RuntimeError("No method finished training.")
    scored = [r for r in results if r.metrics.average_precision is not None]
    best = max(scored, key=lambda r: r.metrics.average_precision or 0) if scored else results[0]
    storage.set_active_model(best.model_id)
    _set(job_id, lambda t: (setattr(t, "status", "done"), setattr(t, "best_model_id", best.model_id)))
    return {"best_model_id": best.model_id, "model_ids": [r.model_id for r in results], "dataset_id": ds.meta.id}


def experiments() -> list[Experiment]:
    models = storage.list_models()
    groups: dict[str, list[ModelSummary]] = {}
    for m in models:
        groups.setdefault(m.job_id or f"single:{m.model_id}", []).append(m)
    live = {tj.job_id: tj for tj in list_jobs()}
    out: list[Experiment] = []
    ap = lambda m: -(m.metrics.average_precision or -1)  # noqa: E731
    for key, ms in groups.items():
        ms = sorted(ms, key=ap)
        tj = live.get(key)
        out.append(Experiment(job_id=key, run_name=ms[0].run_name, dataset_id=ms[0].dataset_id, dataset_name=ms[0].dataset_name, created_at=min(m.created_at for m in ms), status=tj.status if tj else "done", models=ms, best_model_id=ms[0].model_id, train_sample_size=ms[0].train_sample_size, live=tj))
    for jid, tj in live.items():
        if jid not in groups and tj.status in ("queued", "running"):
            out.append(Experiment(job_id=jid, run_name=tj.run_name, dataset_id=tj.dataset_id, dataset_name=tj.dataset_name, created_at=tj.created_at, status=tj.status, models=[], train_sample_size=tj.train_sample_size, live=tj))
    return sorted(out, key=lambda e: e.created_at, reverse=True)
