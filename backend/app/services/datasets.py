"""Turn raw daily columns (synthetic or imported) into a stored dataset: index, features, stats, metadata."""
from __future__ import annotations

import gc
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from app import config
from app.schemas import ColumnInfo, DatasetMeta, DatasetStats, Detection, GenerateRequest, HistBin, NumericStats
from app.services import colstore, features as F, storage, synth

DAILY_COLUMNS = list(synth.DAILY_SPECS)
MEASURE_ROLE = {
    "date_idx": "date", "store_code": "id", "sku_code": "id",
    "pos_scans": "scan", "manual_entry_scans": "scan", "void_count": "scan", "override_count": "scan",
    "after_hours_scans": "scan", "receiving_scans": "scan", "on_promo": "flag",
}
STAT_COLUMNS = ["opening_stock", "received_units", "sold_units", "returned_units", "adjustment_units", "expected_closing", "counted_closing", "pos_scans", "manual_entry_scans", "void_count", "after_hours_scans"]


def _dow(dates: np.ndarray) -> np.ndarray:
    return pd.to_datetime(pd.Series(dates)).dt.dayofweek.to_numpy().astype(np.int8)


def build_index(store_code: np.ndarray, sku_code: np.ndarray) -> dict[str, np.ndarray]:
    series = store_code.astype(np.int64) * 100_000 + sku_code.astype(np.int64)
    change = np.flatnonzero(np.r_[True, series[1:] != series[:-1]])
    offsets = np.r_[change, len(series)].astype(np.int64)
    return {"series_offsets": offsets, "series_store": store_code[change].astype(np.int32), "series_sku": sku_code[change].astype(np.int32)}


def compute_features(ds_dir: Path, daily: dict[str, np.ndarray], skus: pd.DataFrame, dates: np.ndarray, n_stores: int, categories: list[str], on_progress: Callable[[float], None] | None = None) -> list[str]:
    """Engineer features in chunks of whole stores and write them to `features/`. Returns dropped features."""
    n = len(daily["store_code"])
    present = set(daily)
    dropped = [f for f, needs in F.NEEDS.items() if not all(c in present for c in needs)]
    cat_of_sku = np.array([categories.index(c) if c in categories else len(categories) - 1 for c in skus["category"].astype(str)], dtype=np.int16)
    cost_of_sku = skus["unit_cost"].to_numpy(dtype=np.float64)
    dow_of_day = _dow(dates)
    rates = F.global_rates({k: daily[k] for k in ("sold_units", "on_promo", "returned_units") if k in daily})
    out = colstore.preallocate(ds_dir / "features", {k: (np.dtype(np.float32), n) for k in F.FEATURES})
    store = daily["store_code"]
    bounds = np.flatnonzero(np.r_[True, store[1:] != store[:-1]])
    bounds = np.r_[bounds, n]
    step = max(1, config.GEN_BLOCK_STORES)
    for i in range(0, len(bounds) - 1, step):
        a, b = int(bounds[i]), int(bounds[min(i + step, len(bounds) - 1)])
        cols = {k: np.asarray(v[a:b]) for k, v in daily.items()}
        sku = cols["sku_code"].astype(np.int64)
        start = F.series_starts(cols["store_code"].astype(np.int64) * 100_000 + sku)
        feats = F.engineer(cols, start, cost_of_sku[sku], cat_of_sku[sku], dow_of_day[cols["date_idx"].astype(np.int64)], n_stores, len(dates), rates)
        for k in F.FEATURES:
            out[k][a:b] = 0.0 if k in dropped else feats[k]
        del cols, feats
        if on_progress:
            on_progress(b / n)
    colstore.flush(out)
    del out
    gc.collect()
    return dropped


def _hist(values: np.ndarray, lo: float, hi: float, bins: int = 40) -> list[HistBin]:
    counts, edges = np.histogram(np.clip(values, lo, hi), bins=bins, range=(lo, hi))
    return [HistBin(bin_start=round(float(edges[i]), 3), bin_end=round(float(edges[i + 1]), 3), count=int(c)) for i, c in enumerate(counts)]


def compute_stats(daily: dict[str, np.ndarray], features: dict[str, np.ndarray], skus: pd.DataFrame) -> DatasetStats:
    rng = np.random.default_rng(0)
    n = len(daily["store_code"])
    sample = np.sort(rng.choice(n, size=min(n, 400_000), replace=False))
    numeric = {}
    for c in STAT_COLUMNS:
        if c in daily:
            v = np.asarray(daily[c][sample], dtype=np.float64)
            numeric[c] = NumericStats(mean=round(float(v.mean()), 3), std=round(float(v.std()), 3), min=float(v.min()), p50=float(np.percentile(v, 50)), p95=float(np.percentile(v, 95)), max=float(np.asarray(daily[c]).max()))
    shrink = np.asarray(features["shrinkage_pct"][sample], dtype=np.float64)
    cats = skus["category"].astype(str).to_numpy()[np.asarray(daily["sku_code"]).astype(np.int64)]
    vals, counts = np.unique(cats, return_counts=True)
    var = np.asarray(daily["expected_closing"], dtype=np.int64) - np.asarray(daily["counted_closing"], dtype=np.int64)
    cost = skus["unit_cost"].to_numpy(dtype=np.float64)[np.asarray(daily["sku_code"]).astype(np.int64)]
    return DatasetStats(
        numeric=numeric,
        shrinkage_histogram=_hist(shrink[shrink != 0], -40, 60),
        rows_by_category={str(v): int(c) for v, c in zip(vals, counts)},
        units_sold=int(np.asarray(daily["sold_units"], dtype=np.int64).sum()),
        net_variance_units=int(var.sum()),
        net_variance_value_gbp=round(float((var * cost).sum()), 2),
    )


def column_infos(present: list[str], has_truth: bool) -> list[ColumnInfo]:
    from app.assistant.plain_language import FEATURE_LABELS

    cols = [ColumnInfo(name=c, role=MEASURE_ROLE.get(c, "measure"), dtype=str(synth.DAILY_SPECS[c].__name__ if hasattr(synth.DAILY_SPECS[c], "__name__") else synth.DAILY_SPECS[c]), label=FEATURE_LABELS.get(c)) for c in DAILY_COLUMNS if c in present]
    cols += [ColumnInfo(name=f, role="feature" if f in F.DETECT_FEATURES else "context", dtype="float32", label=FEATURE_LABELS.get(f)) for f in F.FEATURES]
    if has_truth:
        cols += [ColumnInfo(name=t, role="ground_truth", dtype=str(synth.TRUTH_SPECS[t].__name__), label=FEATURE_LABELS.get(t)) for t in synth.TRUTH_SPECS]
    return cols


def finalize(
    ds_id: str,
    name: str,
    kind: str,
    stores: pd.DataFrame,
    skus: pd.DataFrame,
    dates: np.ndarray,
    lp_flags: pd.DataFrame,
    params: dict[str, Any],
    detection: Detection | None,
    warnings: list[str],
    on_progress: Callable[[float, str], None] | None = None,
) -> DatasetMeta:
    """Daily (and optional truth) columns are already in ds_dir; build index, features, stats and metadata."""
    ds_dir = storage.dataset_dir(ds_id)
    daily = colstore.open_columns(ds_dir / "daily")
    idx = build_index(np.asarray(daily["store_code"]), np.asarray(daily["sku_code"]))
    colstore.save_index(ds_dir / "index.npz", dates=np.asarray(dates).astype("U10"), **idx)
    stores.to_csv(ds_dir / "stores.csv", index=False)
    skus.to_csv(ds_dir / "skus.csv", index=False)
    lp_flags.to_csv(ds_dir / "lp_flags.csv", index=False)
    categories = list(config.CATEGORIES)
    extra = sorted(set(skus["category"].astype(str)) - set(categories))
    categories += extra
    dropped = compute_features(ds_dir, daily, skus, dates, len(stores), categories, (lambda f: on_progress(f, "Engineering features")) if on_progress else None)
    if detection is not None:
        detection.dropped_features = dropped
    feats = colstore.open_columns(ds_dir / "features")
    if on_progress:
        on_progress(1.0, "Summarising")
    stats = compute_stats(daily, feats, skus)
    has_truth = (ds_dir / "truth").exists()
    truth = colstore.open_columns(ds_dir / "truth") if has_truth else {}
    n_days = len(dates)
    test_idx = int(round(n_days * (1 - config.TEST_WINDOW_SHARE)))
    meta = DatasetMeta(
        id=ds_id,
        name=name,
        kind=kind,  # type: ignore[arg-type]
        created_at=storage.now_iso(),
        n_rows=int(len(daily["store_code"])),
        n_stores=int(len(stores)),
        n_skus=int(len(skus)),
        n_days=int(n_days),
        n_series=int(len(idx["series_offsets"]) - 1),
        date_start=str(dates[0]),
        date_end=str(dates[-1]),
        test_from_date=str(dates[min(test_idx, n_days - 1)]),
        has_truth=has_truth,
        n_anomaly_rows=int((np.asarray(truth["truth_type"]) > 0).sum()) if has_truth else 0,
        n_incidents=int(len(np.unique(np.asarray(truth["truth_incident"])[np.asarray(truth["truth_incident"]) > 0]))) if has_truth else 0,
        n_lp_flags=int(len(lp_flags)),
        feature_columns=[f for f in F.FEATURES if f not in dropped],
        detect_features=[f for f in F.DETECT_FEATURES if f not in dropped],
        categories=categories,
        columns=column_infos(list(daily), has_truth),
        stats=stats,
        params=params,
        detection=detection,
        warnings=warnings,
    )
    del daily, feats, truth
    gc.collect()
    storage.register_dataset(meta)
    return meta


def generate(req: GenerateRequest, ds_id: str, on_progress: Callable[[float, str], None], check_cancelled: Callable[[], None]) -> DatasetMeta:
    p = synth.GenParams(n_stores=req.n_stores, n_skus=req.n_skus, n_days=req.n_days, seed=req.seed, anomaly_multiplier=req.anomaly_multiplier, lp_coverage=req.lp_coverage)
    ds_dir = storage.dataset_dir(ds_id)
    ds_dir.mkdir(parents=True, exist_ok=True)
    out = synth.generate_to_disk(ds_dir, p, lambda f, m: on_progress(f * 0.45, m), check_cancelled)
    check_cancelled()
    name = req.name or f"Synthetic {req.n_stores} stores x {req.n_skus} SKUs x {req.n_days} days (seed {req.seed})"
    return finalize(
        ds_id, name, "synthetic", out["stores"], out["skus"], out["dates"], out["lp_flags"],
        params=req.model_dump(), detection=None, warnings=[],
        on_progress=lambda f, m: on_progress(0.45 + 0.5 * f, m),
    )
