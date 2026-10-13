"""Executive overview: one run's alerts, reviews and stock counts, filtered by period, location and category."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app import config
from app.schemas import ExecutiveSummary
from app.services import storage, triage

_cache: dict[tuple, ExecutiveSummary] = {}


def summary(run_id: str, days: int = 90, region: str | None = None, store_id: str | None = None, category: str | None = None) -> ExecutiveSummary:
    rd = storage.load_run(run_id)
    ds = storage.load_dataset(rd.run.dataset_id)
    reviews = triage.latest(ds.meta.id)
    key = (run_id, days, region, store_id, category, len(reviews), max((r["decided_at"] for r in reviews.values()), default=""))
    if key not in _cache:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = _build(rd, ds, reviews, days, region, store_id, category)
    return _cache[key]


def _build(rd: storage.RunData, ds: storage.Dataset, reviews: dict[str, dict[str, Any]], days: int, region: str | None, store_id: str | None, category: str | None) -> ExecutiveSummary:
    first, end = date.fromisoformat(str(ds.dates[0])), date.fromisoformat(str(ds.dates[-1]))
    start = max(first, end - timedelta(days=days - 1)) if days > 0 else first
    n_days = (end - start).days + 1

    # alerts that started in the period, in the chosen place
    inc = rd.incidents
    if len(inc):
        sd = pd.to_datetime(inc["start_date"]).dt.date
        m = ((sd >= start) & (sd <= end)).to_numpy().copy()
        if region:
            m &= (inc["region"] == region).to_numpy()
        if store_id:
            m &= (inc["store_id"] == store_id).to_numpy()
        if category:
            m &= (inc["category"] == category).to_numpy()
        a = inc[m].copy()
    else:
        a = inc.copy()
    price_col = "unit_price" if "unit_price" in ds.skus else "unit_cost"
    price = dict(zip(ds.skus["sku_id"], ds.skus[price_col].astype(float)))
    a["revenue"] = a["units_at_risk"].astype(float) * a["sku_id"].map(price).fillna(0.0) if len(a) else 0.0
    a["outcome"] = a["alert_key"].map(lambda k: reviews[k]["outcome"] if k in reviews else "open") if len(a) else "open"
    is_open = (a["outcome"] == "open").to_numpy() if len(a) else np.zeros(0, dtype=bool)
    op, closed = a[is_open], a[~is_open]

    # resolution: the clock starts on the last flagged day
    sla = config.EXEC_SLA_DAYS
    within = None
    if len(closed):
        took = closed.apply(lambda r: (date.fromisoformat(reviews[r["alert_key"]]["decided_at"][:10]) - date.fromisoformat(r["end_date"])).days, axis=1)
        within = round(float((took <= sla).mean() * 100), 1)
    late = pd.to_datetime(op["end_date"]).dt.date < end - timedelta(days=sla) if len(op) else pd.Series(dtype=bool)
    overdue = int((op["severity"].isin(["critical", "high"]) & late).sum()) if len(op) else 0

    acc, prev = _accuracy(ds, start, end, region, store_id, category), None
    if days > 0:
        p_end = start - timedelta(days=1)
        p_start = max(first, p_end - timedelta(days=days - 1))
        if p_end >= first and (p_end - p_start).days + 1 >= 7:
            prev = _accuracy(ds, p_start, p_end, region, store_id, category)

    def trend(col: str, label: str, pick: str | None) -> dict[str, Any]:
        # whole weeks counted back from the period end; a leftover stub of 1-6 days at the start is left out
        n_weeks = max(1, n_days // 7)
        weeks = [end - timedelta(days=7 * (n_weeks - 1 - i) + 6) for i in range(n_weeks)]
        rows = [{"week": w.isoformat()} for w in weeks]
        if not len(a):
            return {"series": [], "rows": rows}
        if pick:
            names = [str(a.loc[a[col] == pick, label].iloc[0])] if (a[col] == pick).any() else []
            keys = [pick] if names else []
        else:
            g = op.groupby([col, label])["revenue"].sum().sort_values(ascending=False).head(3) if len(op) else a.groupby([col, label]).size().sort_values(ascending=False).head(3)
            keys, names = [str(k[0]) for k in g.index], [str(k[1]) for k in g.index]
        sd = pd.to_datetime(a["start_date"]).dt.date
        bucket = sd.map(lambda d: n_weeks - 1 - (end - d).days // 7)
        for k, name in zip(keys, names):
            counts = bucket[a[col] == k].value_counts()
            for i, r in enumerate(rows):
                r[name] = int(counts.get(i, 0))
        return {"series": names, "rows": rows}

    top = op.groupby(["store_id", "store_name"])["revenue"].sum().sort_values(ascending=False).head(5) if len(op) else pd.Series(dtype=float)
    stores = ds.stores
    return ExecutiveSummary(
        period={"start": start.isoformat(), "end": end.isoformat(), "days": n_days},
        options={
            "regions": sorted(stores["region"].dropna().unique().tolist()) if "region" in stores else [],
            "stores": [{"store_id": r.store_id, "store_name": r.store_name} for r in stores.itertuples()],
            "categories": ds.meta.categories,
        },
        revenue_at_risk_gbp=round(float(op["revenue"].sum()), 2) if len(op) else 0.0,
        value_at_risk_gbp=round(float(op["value_at_risk_gbp"].sum()), 2) if len(op) else 0.0,
        open_cases=int(len(op)),
        threshold_gbp=config.EXEC_REVENUE_RED_GBP,
        loss_prevented_gbp=round(float(closed.loc[closed["outcome"] != "false_alarm", "revenue"].sum()), 2) if len(closed) else 0.0,
        closed_cases=int(len(closed)),
        inventory_accuracy_pct=acc,
        accuracy_delta_pp=round(acc - prev, 1) if acc is not None and prev is not None else None,
        sla_within_pct=within,
        sla_target_pct=config.EXEC_SLA_TARGET_PCT,
        sla_days=sla,
        overdue_cases=overdue,
        store_trend=trend("store_id", "store_name", store_id),
        category_trend=trend("category", "category", category),
        top_locations=[{"store_id": k[0], "label": k[1], "value_gbp": round(float(v), 2)} for k, v in top.items()],
    )


def _accuracy(ds: storage.Dataset, start: date, end: date, region: str | None, store_id: str | None, category: str | None) -> float | None:
    """Share of store-SKU-days whose count matched the books within max(1 unit, 2%)."""
    lo, hi = np.searchsorted(ds.dates, start.isoformat()), np.searchsorted(ds.dates, end.isoformat(), side="right")
    di = np.asarray(ds.daily["date_idx"])
    m = (di >= lo) & (di < hi)
    if region or store_id:
        st = ds.stores
        ok = np.ones(len(st), dtype=bool)
        if region:
            ok &= (st["region"] == region).to_numpy()
        if store_id:
            ok &= (st["store_id"] == store_id).to_numpy()
        m &= ok[np.asarray(ds.daily["store_code"]).astype(np.int64)]
    if category:
        m &= (ds.skus["category"] == category).to_numpy()[np.asarray(ds.daily["sku_code"]).astype(np.int64)]
    if not m.any():
        return None
    exp = np.asarray(ds.daily["expected_closing"])[m].astype(np.float64)
    cnt = np.asarray(ds.daily["counted_closing"])[m].astype(np.float64)
    good = np.abs(exp - cnt) <= np.maximum(1.0, config.EXEC_ACCURACY_TOLERANCE * np.abs(exp))
    return round(float(good.mean() * 100), 1)
