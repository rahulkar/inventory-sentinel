"""Detection runs: score every row with a model, group flagged days into incidents (alerts), build dashboard data."""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from app import config
from app.schemas import Alert, AlertPage, DetectionRun, DetectRequest, Job, RunEvaluation, RunKpis, SeriesMatch, SeriesPoint, SeriesResponse
from app.services import calibration, explain, jobs, storage, triage
from app.services import features as F
from app.services.training import percentile_of, score_chunked

SEV_NAME = {1: "medium", 2: "high", 3: "critical"}
TRUTH_TO_TYPE = {t: t for t in config.ANOMALY_TYPES}


def resolve_model(model_id: str | None) -> str:
    mid = model_id or storage.get_active_model_id()
    if not mid or storage.get_model_summary(mid) is None:
        raise LookupError("No model selected. Train a model first (or pick one).")
    return mid


def start_job(req: DetectRequest) -> Job:
    meta = storage.get_dataset_meta(req.dataset_id)
    if meta is None:
        raise LookupError("Dataset not found.")
    model_id = resolve_model(req.model_id)
    m = storage.get_model(model_id)
    assert m is not None
    if m.dataset_id != meta.id:
        # models trained on one dataset can score another one with the same schema
        pass
    from app.services import registry

    per_1m = m.metrics.score_seconds_per_1m or (registry.REGISTRY[m.key].score_seconds_per_1m if m.key in registry.REGISTRY else 30.0)
    est = meta.n_rows / 1e6 * (per_1m + config.TIMING["detect_overhead_s_per_1m"]) + 5
    run_id = storage.new_id("run")
    return jobs.submit(
        "detect", f"Detect anomalies with {m.label} on {meta.name}", lambda ctx: _run(ctx, meta.id, model_id, run_id),
        params={"dataset_id": meta.id, "model_id": model_id, "run_id": run_id},
        steps=[("load", "Loading model and features"), ("score", f"Scoring {meta.n_rows:,} rows"), ("incidents", "Grouping flagged days into incidents"), ("aggregate", "Building the dashboard"), ("save", "Saving the run")],
        estimate_seconds=round(est, 1),
    )


def _row_series(ds: storage.Dataset, rows: np.ndarray) -> np.ndarray:
    return np.searchsorted(ds.series_offsets, rows, side="right") - 1


def build_incidents(ds: storage.Dataset, meta, score: np.ndarray, pct: np.ndarray, sev: np.ndarray) -> pd.DataFrame:
    flagged = np.flatnonzero(sev > 0)
    if len(flagged) == 0:
        return pd.DataFrame(columns=storage.INCIDENT_COLUMNS)  # keep the header so the saved run loads back
    series = _row_series(ds, flagged)
    day = np.asarray(ds.daily["date_idx"])[flagged].astype(np.int64)
    new = np.r_[True, (series[1:] != series[:-1]) | (day[1:] - day[:-1] > config.INCIDENT_GAP_DAYS + 1)]
    inc_id = np.cumsum(new) - 1
    n_inc = int(inc_id[-1] + 1)
    exp = np.asarray(ds.daily["expected_closing"])[flagged].astype(np.int64)
    cnt = np.asarray(ds.daily["counted_closing"])[flagged].astype(np.int64)
    var = exp - cnt
    sku = np.asarray(ds.daily["sku_code"])[flagged].astype(np.int64)
    store = np.asarray(ds.daily["store_code"])[flagged].astype(np.int64)
    cost = ds.skus["unit_cost"].to_numpy(dtype=np.float64)[sku]
    sc = score[flagged]
    # per-incident aggregates with bincount
    units = np.bincount(inc_id, weights=np.maximum(var, 0), minlength=n_inc)
    value = np.bincount(inc_id, weights=np.maximum(var, 0) * cost, minlength=n_inc)
    net = np.bincount(inc_id, weights=var, minlength=n_inc)
    absv = np.bincount(inc_id, weights=np.abs(var), minlength=n_inc)
    first = np.flatnonzero(new)
    last = np.r_[first[1:] - 1, len(flagged) - 1]
    # peak row = highest score within the incident
    order = np.lexsort((-sc, inc_id))
    peak_pos = order[np.r_[True, inc_id[order][1:] != inc_id[order][:-1]]]
    peak_rows = flagged[peak_pos]
    sev_max = np.maximum.reduceat(sev[flagged], first)
    rec = np.asarray(ds.daily["received_units"])[peak_rows]
    feats = {f: np.asarray(ds.features[f])[peak_rows] for f in F.DETECT_FEATURES}
    raw_cols = ["expected_closing", "counted_closing", "sold_units", "received_units", "receiving_scans", "adjustment_units", "returned_units", "manual_entry_scans", "pos_scans", "void_count", "override_count", "after_hours_scans"]
    raws = {c: np.asarray(ds.daily[c])[peak_rows] for c in raw_cols if c in ds.daily}
    st = ds.stores
    sk = ds.skus
    p_true = calibration.predict(meta.calibration, pct[peak_rows])
    has_truth = bool(ds.truth)
    if has_truth:
        tt = np.asarray(ds.truth["truth_type"])[flagged]
        truth_major = np.zeros(n_inc, dtype=np.int64)
        pos = tt > 0
        if pos.any():
            # most common non-zero truth type per incident (ties -> first)
            pairs = pd.DataFrame({"i": inc_id[pos], "t": tt[pos]}).value_counts().reset_index().sort_values(["i", "count"], ascending=[True, False]).drop_duplicates("i")
            truth_major[pairs["i"].to_numpy()] = pairs["t"].to_numpy()
    rows = []
    dates = ds.dates
    for i in range(n_inc):
        pr = int(peak_rows[i])
        a, b = int(first[i]), int(last[i])
        n_days = int(day[b] - day[a] + 1)
        f_peak = {f: float(feats[f][i]) for f in F.DETECT_FEATURES}
        r_peak = {c: int(raws[c][i]) for c in raws}
        cat = str(sk["category"].iat[sku[a]])
        likely, conf = explain.guess_type(f_peak, n_days, float(net[i]), float(absv[i]), bool(rec[i] > 0))
        rows.append({
            "store_code": int(store[a]), "sku_code": int(sku[a]),
            "store_id": str(st["store_id"].iat[store[a]]), "store_name": str(st["store_name"].iat[store[a]]), "region": str(st["region"].iat[store[a]]) if "region" in st else "",
            "warehouse_team": str(st["warehouse_team"].iat[store[a]]) if "warehouse_team" in st else "All stores",
            "sku_id": str(sk["sku_id"].iat[sku[a]]), "sku_name": str(sk["sku_name"].iat[sku[a]]) if "sku_name" in sk else str(sk["sku_id"].iat[sku[a]]), "category": cat,
            "start_date": str(dates[day[a]]), "end_date": str(dates[day[b]]), "n_days": n_days, "n_flagged_days": int(b - a + 1),
            "peak_row": pr, "peak_score": round(float(sc[peak_pos[i]]), 6), "peak_percentile": round(float(pct[pr]), 6), "severity": SEV_NAME[int(sev_max[i])],
            "units_at_risk": int(units[i]), "value_at_risk_gbp": round(float(value[i]), 2), "net_variance_units": int(net[i]),
            "likely_type": likely, "type_confidence": conf,
            "reasons": " || ".join(explain.reasons(f_peak, r_peak, meta.feature_baseline, cat)),
            "p_true": round(float(p_true[i]), 4),
            "truth_type": config.ANOMALY_TYPES[int(truth_major[i])] if has_truth else "",
            "start_day": int(day[a]),
        })
    df = pd.DataFrame(rows)
    sev_rank = df["severity"].map({"critical": 3, "high": 2, "medium": 1})
    df = df.assign(_r=sev_rank).sort_values(["_r", "peak_percentile", "value_at_risk_gbp"], ascending=[False, False, False]).drop(columns="_r").reset_index(drop=True)
    df.insert(0, "alert_id", [f"A{i + 1:06d}" for i in range(len(df))])
    df.insert(1, "alert_key", df["store_id"] + "|" + df["sku_id"] + "|" + df["start_date"])
    return df


def aggregates(ds: storage.Dataset, inc: pd.DataFrame, sev: np.ndarray) -> dict[str, Any]:
    dates = ds.dates
    n_days = len(dates)
    flagged = np.flatnonzero(sev > 0)
    day = np.asarray(ds.daily["date_idx"])[flagged].astype(np.int64)
    s = sev[flagged].astype(np.int64)
    var = np.asarray(ds.daily["expected_closing"])[flagged].astype(np.int64) - np.asarray(ds.daily["counted_closing"])[flagged].astype(np.int64)
    cost = ds.skus["unit_cost"].to_numpy(dtype=np.float64)[np.asarray(ds.daily["sku_code"])[flagged].astype(np.int64)]
    trend = []
    by_sev = {name: np.bincount(day[s == k], minlength=n_days) for k, name in SEV_NAME.items()}
    val = np.bincount(day, weights=np.maximum(var, 0) * cost, minlength=n_days)
    types = sorted(set(inc["likely_type"])) if len(inc) else []
    by_type = {t: np.bincount(inc.loc[inc["likely_type"] == t, "start_day"].to_numpy(dtype=np.int64), minlength=n_days) for t in types}
    for d in range(n_days):
        row = {"date": str(dates[d]), "value_gbp": round(float(val[d]), 2), **{k: int(v[d]) for k, v in by_sev.items()}}
        row.update({f"type:{t}": int(v[d]) for t, v in by_type.items()})
        trend.append(row)
    heat = []
    if len(inc):
        g = inc.groupby(["store_id", "store_name", "category"]).agg(alerts=("alert_id", "size"), value=("value_at_risk_gbp", "sum")).reset_index()
        heat = [{"store_id": r.store_id, "store_name": r.store_name, "category": r.category, "alerts": int(r.alerts), "value_gbp": round(float(r.value), 2)} for r in g.itertuples()]

    def top(col: str, label_col: str | None = None, n: int = 20) -> list[dict[str, Any]]:
        if not len(inc):
            return []
        keys = [col] + ([label_col] if label_col else [])
        g = inc.groupby(keys).agg(alerts=("alert_id", "size"), value=("value_at_risk_gbp", "sum"), critical=("severity", lambda x: int((x == "critical").sum()))).reset_index().sort_values("value", ascending=False).head(n)
        return [{"key": str(r[col]), "label": str(r[label_col]) if label_col else str(r[col]), "alerts": int(r["alerts"]), "value_gbp": round(float(r["value"]), 2), "critical": int(r["critical"])} for _, r in g.iterrows()]

    return {
        "trend": trend,
        "types": types,
        "heatmap": heat,
        "categories": ds.meta.categories,
        "stores": [{"store_id": r.store_id, "store_name": r.store_name} for r in ds.stores.itertuples()],
        "by_region": top("region", n=12),
        "top_stores": top("store_id", "store_name"),
        "top_skus": top("sku_id", "sku_name"),
        "top_teams": top("warehouse_team", n=12),
        "by_category": top("category", n=20),
    }


def evaluate_run(ds: storage.Dataset, inc: pd.DataFrame, sev: np.ndarray) -> RunEvaluation | None:
    if not ds.truth or not len(inc):
        return None
    test_from = ds.test_from_idx
    date_idx = np.asarray(ds.daily["date_idx"])
    ti = np.asarray(ds.truth["truth_incident"])
    tt = np.asarray(ds.truth["truth_type"])
    win = date_idx >= test_from
    all_inc = np.unique(ti[win & (ti > 0)])
    hit_inc = np.unique(ti[win & (ti > 0) & (sev > 0)])
    cost = ds.skus["unit_cost"].to_numpy(dtype=np.float64)[np.asarray(ds.daily["sku_code"]).astype(np.int64)]
    loss = np.asarray(ds.truth["truth_loss_units"]).astype(np.float64) * cost
    tot = loss[win & (tt > 0)].sum()
    cap = loss[win & (tt > 0) & (sev > 0)].sum()
    w = inc[inc["start_day"] >= test_from]
    prec = float((w["truth_type"] != "none").mean()) if len(w) else None
    tp = w[w["truth_type"] != "none"]
    acc = float((tp["likely_type"] == tp["truth_type"]).mean()) if len(tp) else None
    return RunEvaluation(label_source="ground_truth", window=f"evaluation window from {ds.meta.test_from_date}", incident_recall=round(len(hit_inc) / max(len(all_inc), 1), 4), alert_precision=round(prec, 4) if prec is not None else None, value_captured_pct=round(cap / tot * 100, 2) if tot > 0 else None, type_accuracy=round(acc, 4) if acc is not None else None)


def _run(ctx: jobs.JobContext, ds_id: str, model_id: str, run_id: str) -> dict[str, Any]:
    t0 = time.time()
    ctx.step("load", "Loading model and features")
    ds = storage.load_dataset(ds_id)
    meta = storage.get_model(model_id)
    pipe = storage.load_pipeline(model_id)
    ctx.progress(3)
    ctx.step("score", f"Scoring {ds.meta.n_rows:,} rows")
    score = score_chunked(pipe, ds, on_progress=lambda f: ctx.progress(3 + 80 * f), check=ctx.check_cancelled)
    pct = percentile_of(meta, score).astype(np.float32)
    thr = meta.thresholds
    sev = np.where(score >= thr.critical, 3, np.where(score >= thr.high, 2, np.where(score >= thr.alert, 1, 0))).astype(np.int8)
    ctx.step("incidents", "Grouping flagged days into incidents")
    inc = build_incidents(ds, meta, score, pct, sev)
    ctx.progress(90)
    ctx.step("aggregate", "Building the dashboard")
    agg = aggregates(ds, inc, sev)
    ev = evaluate_run(ds, inc, sev)
    ctx.progress(96)
    ctx.step("save", "Saving the run")
    kpis = RunKpis(
        rows_scored=int(ds.meta.n_rows), flagged_rows=int((sev > 0).sum()), incidents=int(len(inc)),
        value_at_risk_gbp=round(float(inc["value_at_risk_gbp"].sum()), 2) if len(inc) else 0.0,
        pct_rows_flagged=round(float((sev > 0).mean() * 100), 3), stores_affected=int(inc["store_id"].nunique()) if len(inc) else 0,
        by_severity={k: int((inc["severity"] == k).sum()) for k in ("critical", "high", "medium")} if len(inc) else {},
        by_type=inc["likely_type"].value_counts().to_dict() if len(inc) else {},
    )
    run = DetectionRun(
        run_id=run_id, dataset_id=ds.meta.id, dataset_name=ds.meta.name, model_id=model_id, model_name=meta.name, model_label=meta.label,
        created_at=storage.now_iso(), thresholds=thr, kpis=kpis, evaluation=ev, seconds=round(time.time() - t0, 1),
        warnings=[] if len(inc) else ["No day scored above the alert threshold."],
    )
    storage.save_run(run, {"score": score, "percentile": pct, "severity": sev}, inc, agg)
    return {"run_id": run_id, "incidents": kpis.incidents, "value_at_risk_gbp": kpis.value_at_risk_gbp, "dataset_id": ds.meta.id, "model_id": model_id}


# ---------------------------------------------------------------- reading runs
def _status_map(dataset_id: str) -> dict[str, str]:
    return {k: v["outcome"] for k, v in triage.latest(dataset_id).items()}


def to_alert(r: Any, status: dict[str, str], answer_key: bool) -> Alert:
    d = r if isinstance(r, dict) else r._asdict() if hasattr(r, "_asdict") else dict(r)
    reasons = [x for x in str(d.get("reasons", "")).split(" || ") if x]
    return Alert(
        alert_id=d["alert_id"], alert_key=d["alert_key"], store_id=str(d["store_id"]), store_name=d["store_name"], region=str(d.get("region", "")),
        warehouse_team=str(d.get("warehouse_team", "")), sku_id=str(d["sku_id"]), sku_name=d["sku_name"], category=d["category"],
        start_date=d["start_date"], end_date=d["end_date"], n_days=int(d["n_days"]), peak_score=float(d["peak_score"]), peak_percentile=float(d["peak_percentile"]),
        severity=d["severity"], units_at_risk=int(d["units_at_risk"]), value_at_risk_gbp=float(d["value_at_risk_gbp"]), likely_type=d["likely_type"],
        type_confidence=float(d["type_confidence"]), reasons=reasons, p_true=float(d["p_true"]), status=status.get(d["alert_key"], "open"),
        truth_type=(d.get("truth_type") or None) if answer_key else None,
    )


def list_alerts(run_id: str, *, severity: list[str] | None = None, likely_type: list[str] | None = None, store_id: str | None = None, team: str | None = None, category: str | None = None, status: str | None = None, q: str | None = None, sort: str = "priority", limit: int = 50, offset: int = 0, answer_key: bool = False) -> AlertPage:
    rd = storage.load_run(run_id)
    df = rd.incidents
    if not len(df):
        return AlertPage(total=0, alerts=[])
    st = _status_map(rd.run.dataset_id)
    m = np.ones(len(df), dtype=bool)
    if severity:
        m &= df["severity"].isin(severity).to_numpy()
    if likely_type:
        m &= df["likely_type"].isin(likely_type).to_numpy()
    if store_id:
        m &= (df["store_id"] == store_id).to_numpy()
    if team:
        m &= (df["warehouse_team"] == team).to_numpy()
    if category:
        m &= (df["category"] == category).to_numpy()
    if status:
        s = df["alert_key"].map(lambda k: st.get(k, "open"))
        m &= ((s == "open") if status == "open" else (s != "open") if status == "reviewed" else (s == status)).to_numpy()
    if q:
        ql = q.lower()
        m &= df["store_id"].str.lower().str.contains(ql, regex=False).to_numpy() | df["sku_id"].str.lower().str.contains(ql, regex=False).to_numpy() | df["sku_name"].str.lower().str.contains(ql, regex=False).to_numpy() | df["store_name"].str.lower().str.contains(ql, regex=False).to_numpy() | (df["alert_id"].str.lower() == ql).to_numpy()
    sub = df[m]
    if sort == "plan":
        from app.services import planner

        rank = planner.rank_by_alert(run_id)
        sub = sub.assign(_r=sub["alert_id"].map(lambda a: rank.get(a, 1 << 30))).sort_values("_r").drop(columns="_r")
    elif sort == "value":
        sub = sub.sort_values("value_at_risk_gbp", ascending=False)
    elif sort == "p_true":
        sub = sub.sort_values(["p_true", "value_at_risk_gbp"], ascending=False)
    elif sort == "recent":
        sub = sub.sort_values(["start_date", "peak_percentile"], ascending=False)
    page = sub.iloc[offset : offset + limit]
    return AlertPage(total=int(len(sub)), alerts=[to_alert(r, st, answer_key) for r in page.to_dict("records")])


def get_alert(run_id: str, alert_id: str, answer_key: bool = False) -> Alert:
    rd = storage.load_run(run_id)
    hit = rd.incidents[rd.incidents["alert_id"] == alert_id]
    if not len(hit):
        raise LookupError(f"Alert {alert_id} not found in run {run_id}")
    return to_alert(hit.iloc[0].to_dict(), _status_map(rd.run.dataset_id), answer_key)


def series(run_id: str, store_id: str, sku_id: str, answer_key: bool = False) -> SeriesResponse:
    rd = storage.load_run(run_id)
    ds = storage.load_dataset(rd.run.dataset_id)
    si = ds.series_index(store_id, sku_id)
    if si is None:
        raise LookupError(f"{store_id} / {sku_id} not found")
    a, b = int(ds.series_offsets[si]), int(ds.series_offsets[si + 1])
    d = {k: np.asarray(v[a:b]) for k, v in ds.daily.items()}
    lp = {}
    if len(ds.lp_flags):
        fl = ds.lp_flags[(ds.lp_flags["store_id"].astype(str) == store_id) & (ds.lp_flags["sku_id"].astype(str) == sku_id)]
        lp = {int(r.date_idx): str(r.flag_type) for r in fl.itertuples()}
    tt = np.asarray(ds.truth["truth_type"][a:b]) if (answer_key and ds.truth) else None
    pts = []
    for i in range(b - a):
        di = int(d["date_idx"][i])
        g = lambda k: int(d[k][i]) if k in d else 0  # noqa: E731
        pts.append(SeriesPoint(
            date=str(ds.dates[di]), opening_stock=g("opening_stock"), received_units=g("received_units"), sold_units=g("sold_units"), returned_units=g("returned_units"),
            adjustment_units=g("adjustment_units"), expected_closing=g("expected_closing"), counted_closing=g("counted_closing"), variance_units=g("expected_closing") - g("counted_closing"),
            pos_scans=g("pos_scans"), manual_entry_scans=g("manual_entry_scans"), void_count=g("void_count"), override_count=g("override_count"), after_hours_scans=g("after_hours_scans"),
            receiving_scans=g("receiving_scans"), on_promo=g("on_promo"), score=round(float(rd.score[a + i]), 6), percentile=round(float(rd.percentile[a + i]), 5),
            severity=int(rd.severity[a + i]), lp_flag=lp.get(di), truth_type=(config.ANOMALY_TYPES[int(tt[i])] if tt is not None and tt[i] > 0 else None),
        ))
    meta = storage.get_model(rd.run.model_id)
    cat = str(ds.skus["category"].iat[int(ds.series_sku[si])])
    reasons = {}
    for i in np.flatnonzero(np.asarray(rd.severity[a:b]) > 0)[:60]:
        r = a + int(i)
        f = {k: float(ds.features[k][r]) for k in F.DETECT_FEATURES}
        raw = {k: int(ds.daily[k][r]) for k in ds.daily}
        reasons[str(ds.dates[int(d["date_idx"][i])])] = explain.reasons(f, raw, meta.feature_baseline if meta else {}, cat)
    inc = rd.incidents
    mine = inc[(inc["store_id"] == store_id) & (inc["sku_id"] == sku_id)] if len(inc) else inc
    st = _status_map(rd.run.dataset_id)
    sku_row = ds.skus.iloc[int(ds.series_sku[si])]
    store_row = ds.stores.iloc[int(ds.series_store[si])]
    return SeriesResponse(
        store_id=store_id, store_name=str(store_row["store_name"]), sku_id=sku_id, sku_name=str(sku_row.get("sku_name", sku_id)), category=cat,
        unit_cost=float(sku_row["unit_cost"]), points=pts, alerts=[to_alert(r, st, answer_key) for r in mine.to_dict("records")] if len(mine) else [],
        flagged_reasons=reasons, triage=[v for v in triage.latest(rd.run.dataset_id).values() if v.get("store_id") == store_id and v.get("sku_id") == sku_id],
    )


def search(run_id: str, q: str, limit: int = 20) -> list[SeriesMatch]:
    rd = storage.load_run(run_id)
    ds = storage.load_dataset(rd.run.dataset_id)
    ql = (q or "").strip().lower()
    stores, skus = ds.stores, ds.skus
    terms = ql.replace(",", " ").split()
    st_hit = np.ones(len(stores), dtype=bool)
    sk_hit = np.ones(len(skus), dtype=bool)
    for t in terms:
        s_m = stores["store_id"].str.lower().str.contains(t, regex=False) | stores["store_name"].str.lower().str.contains(t, regex=False)
        k_m = skus["sku_id"].str.lower().str.contains(t, regex=False) | skus.get("sku_name", skus["sku_id"]).astype(str).str.lower().str.contains(t, regex=False) | skus["category"].astype(str).str.lower().str.contains(t, regex=False)
        if s_m.any() and not k_m.any():
            st_hit &= s_m.to_numpy()
        elif k_m.any() and not s_m.any():
            sk_hit &= k_m.to_numpy()
        else:
            st_hit &= s_m.to_numpy() | ~k_m.any()
            sk_hit &= k_m.to_numpy() | ~s_m.any()
    inc = rd.incidents
    counts = inc.groupby(["store_id", "sku_id"]).size().to_dict() if len(inc) else {}
    out = []
    sids, kids = np.flatnonzero(st_hit), np.flatnonzero(sk_hit)
    # prefer series with alerts
    pairs = [(s, k) for s in sids for k in kids] if len(sids) * len(kids) <= 50_000 else [(s, k) for s in sids[:50] for k in kids[:200]]
    pairs.sort(key=lambda p: -counts.get((stores["store_id"].iat[p[0]], skus["sku_id"].iat[p[1]]), 0))
    for s, k in pairs[:limit]:
        sid, kid = str(stores["store_id"].iat[s]), str(skus["sku_id"].iat[k])
        out.append(SeriesMatch(store_id=sid, store_name=str(stores["store_name"].iat[s]), sku_id=kid, sku_name=str(skus.get("sku_name", skus["sku_id"]).iat[k]), category=str(skus["category"].iat[k]), n_alerts=int(counts.get((sid, kid), 0))))
    return out


def recalibrate(run_id: str) -> dict[str, Any]:
    """Refresh P(true) of every alert from the team's triage decisions on this dataset."""
    rd = storage.load_run(run_id)
    meta = storage.get_model(rd.run.model_id)
    dec = triage.latest(rd.run.dataset_id)
    inc = rd.incidents.copy()
    lab = inc["alert_key"].map(lambda k: dec.get(k, {}).get("outcome"))
    known = lab.notna()
    if known.sum() < 10:
        raise ValueError("At least 10 reviewed alerts are needed to recalibrate.")
    y = (lab[known] != "false_alarm").astype(float).to_numpy()
    cal = calibration.fit(inc.loc[known, "peak_percentile"].to_numpy(), y, None, 1 - meta.alert_rate, "triage", f"From {int(known.sum())} alerts your team reviewed.")
    inc["p_true"] = np.round(calibration.predict(cal, inc["peak_percentile"].to_numpy()), 4)
    storage.update_run_incidents(run_id, inc)
    meta.calibration = cal
    storage.update_model_meta(meta)
    return {"run_id": run_id, "reviewed": int(known.sum()), "precision": round(float(y.mean()), 4), "calibration": cal.model_dump()}
