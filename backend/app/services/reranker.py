"""Retrain with feedback: a supervised re-ranker on top of an unsupervised detector, judged on unreviewed days."""
from __future__ import annotations

import time
from typing import Any

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

from app import config
from app.schemas import Job, ModelMeta, RetrainRequest
from app.services import calibration, jobs, storage, triage
from app.services import features as F
from app.services.detectors import FeedbackReranker, pipeline_score
from app.services.training import EvalSet, QUANTILE_LEVELS, evaluate, feature_matrix, percentile_of, thresholds_from, train_sample


def rows_for(ds: storage.Dataset, store_id: str, sku_id: str, start: str, end: str) -> np.ndarray:
    si = ds.series_index(store_id, sku_id)
    if si is None:
        return np.zeros(0, dtype=np.int64)
    a, b = int(ds.series_offsets[si]), int(ds.series_offsets[si + 1])
    d0, d1 = int(np.searchsorted(ds.dates, start)), int(np.searchsorted(ds.dates, end))
    di = np.asarray(ds.daily["date_idx"][a:b])
    return a + np.flatnonzero((di >= d0) & (di <= d1))


def start_job(model_id: str, req: RetrainRequest) -> Job:
    base = storage.get_model(model_id)
    if base is None:
        raise LookupError("Model not found.")
    if base.key == "reranker":
        raise ValueError("Pick the unsupervised model the re-ranker should sit on (not another re-ranker).")
    s = triage.summary(base.dataset_id, None)
    if not s.can_retrain:
        raise ValueError(s.retrain_reason or "Not enough feedback yet.")
    return jobs.submit(
        "retrain", f"Retrain {base.label} with {s.reviewed} team decisions", lambda ctx: _run(ctx, model_id, req), params={"model_id": model_id, **req.model_dump()},
        steps=[("labels", "Collecting feedback labels"), ("fit", "Training the re-ranker"), ("evaluate", "Comparing on days nobody reviewed"), ("save", "Saving")], estimate_seconds=40,
    )


def _classifier(seed: int, n_pos: int, n_neg: int):
    try:
        from lightgbm import LGBMClassifier

        return LGBMClassifier(n_estimators=200, num_leaves=15, min_child_samples=20, learning_rate=0.05, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=seed, verbose=-1), "LightGBM"
    except Exception:  # noqa: BLE001
        from sklearn.linear_model import LogisticRegression

        return LogisticRegression(max_iter=500, class_weight="balanced"), "logistic regression"


def _run(ctx: jobs.JobContext, model_id: str, req: RetrainRequest) -> dict[str, Any]:
    ctx.step("labels", "Collecting feedback labels")
    base = storage.get_model(model_id)
    ds = storage.load_dataset(base.dataset_id)
    base_pipe = storage.load_pipeline(model_id)
    dec = triage.latest(ds.meta.id)
    pos_rows, neg_rows = [], []
    for r in dec.values():
        rows = rows_for(ds, r["store_id"], r["sku_id"], r["start_date"], r["end_date"])
        (neg_rows if r["outcome"] == "false_alarm" else pos_rows).append(rows)
    pos = np.unique(np.concatenate(pos_rows)) if pos_rows else np.zeros(0, dtype=np.int64)
    neg = np.unique(np.concatenate(neg_rows)) if neg_rows else np.zeros(0, dtype=np.int64)
    triaged = np.unique(np.r_[pos, neg]).astype(np.int64)
    date_idx = np.asarray(ds.daily["date_idx"])
    lp = np.flatnonzero(ds.lp_mask() & (date_idx < ds.test_from_idx))
    lp = np.setdiff1d(lp, triaged)
    rng = np.random.default_rng(42)
    unl = train_sample(ds, 20_000, True, 7, extra_exclude=triaged)
    rows = np.r_[pos, lp, neg, unl].astype(np.int64)
    y = np.r_[np.ones(len(pos)), np.ones(len(lp)), np.zeros(len(neg)), np.zeros(len(unl))]
    w = np.r_[np.ones(len(pos)), np.full(len(lp), 0.7), np.ones(len(neg)), np.full(len(unl), 0.2)]
    X = feature_matrix(ds, rows)
    base_pct = percentile_of(base, pipeline_score(base_pipe, X))
    ctx.progress(25)
    ctx.step("fit", "Training the re-ranker")
    clf, clf_name = _classifier(42, int(y.sum()), int((1 - y).sum()))
    Z = np.column_stack([X, base_pct.astype(np.float32)])
    try:
        clf.fit(Z, y, sample_weight=w)
    except TypeError:
        clf.fit(Z, y)
    rr = FeedbackReranker(alpha=req.alpha).setup(base_pipe, clf, np.asarray(base.score_quantiles), np.asarray(base.quantile_levels))
    pipe = Pipeline([("pre", ColumnTransformer([("pass", "passthrough", list(range(len(F.FEATURES))))])), ("model", rr)])
    pipe.fit(X[:10])
    tr = train_sample(ds, min(base.train_sample_size or config.DEFAULT_TRAIN_SAMPLE, 200_000), True, 42, extra_exclude=triaged)
    Xtr = feature_matrix(ds, tr)
    s_tr = pipeline_score(pipe, Xtr)
    q = np.quantile(s_tr, QUANTILE_LEVELS)
    thr = thresholds_from(q, QUANTILE_LEVELS, base.alert_rate)
    ctx.progress(55)
    ctx.step("evaluate", "Comparing on days nobody reviewed")
    es = EvalSet(ds, rng, tr, exclude_rows=triaged)
    Xev = feature_matrix(ds, es.rows)
    t1 = time.time()
    s_new = pipeline_score(pipe, Xev)
    per_1m = (time.time() - t1) / max(len(Xev), 1) * 1_000_000
    s_base = pipeline_score(base_pipe, Xev)
    m_new = evaluate(es, s_new, thr, None)
    m_base = evaluate(es, s_base, base.thresholds, None)
    m_new.fit_seconds = 0.0
    m_new.score_seconds_per_1m = round(per_1m, 1)
    m_new.n_train = int(len(rows))
    ctx.progress(85)
    ctx.step("save", "Saving")
    keys = ["average_precision", "precision_at_k", "incident_recall", "value_captured_pct", "recall_at_threshold"]
    fe = {
        "window": f"evaluation window from {ds.meta.test_from_date}, excluding every day inside a reviewed alert",
        "label_source": es.source,
        "base": {k: getattr(m_base, k) for k in keys},
        "reranker": {k: getattr(m_new, k) for k in keys},
        "n_labels": {"confirmed": int(len(pos)), "false_alarm": int(len(neg)), "lp_flagged": int(len(lp)), "unlabelled": int(len(unl))},
        "classifier": clf_name,
        "alpha": req.alpha,
    }
    meta = ModelMeta(
        model_id=storage.new_id("m"), name=f"Feedback re-ranker on {base.label} · {time.strftime('%H:%M')}", key="reranker", label=f"Feedback re-ranker ({base.label})",
        dataset_id=ds.meta.id, dataset_name=ds.meta.name, run_name=req.run_name or f"Feedback {time.strftime('%H:%M:%S')}", created_at=storage.now_iso(), metrics=m_new,
        engine=getattr(base_pipe.named_steps["model"], "engine_", "sklearn"), job_id=ctx.job_id, parent_model_id=model_id, train_sample_size=int(len(rows)),
        params={"alpha": req.alpha, "classifier": clf_name}, feature_columns=list(F.FEATURES), input_features=list(F.FEATURES) + ["base_percentile"], categories=ds.meta.categories,
        thresholds=thr, score_quantiles=[float(x) for x in q], quantile_levels=[float(x) for x in QUANTILE_LEVELS], importances=base.importances, feature_baseline=base.feature_baseline,
        alert_rate=base.alert_rate, test_from_date=ds.meta.test_from_date, onnx_ok=False, onnx_reason="The feedback re-ranker chains two models (a detector and a classifier); use the joblib bundle.",
        notes=[f"Trained on {len(pos)} confirmed and {len(neg)} false-alarm days from team feedback, {len(lp)} loss-prevention-flagged days and {len(unl)} unlabelled days.", f"Judged on {fe['window']}."],
        feedback_eval=fe,
    )
    pct = percentile_of(meta, s_new)
    if es.source != "none" and es.n_pos:
        meta.calibration = calibration.fit(pct, es.y, es.w, 1 - base.alert_rate, es.source, "From the evaluation window (days nobody reviewed).")
    else:
        meta.calibration = base.calibration
    storage.save_model(meta, pipe)
    storage.set_active_model(meta.model_id)
    return {"model_id": meta.model_id, "parent_model_id": model_id, "feedback_eval": fe}
