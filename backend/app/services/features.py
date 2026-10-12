"""Inventory features, computed with segment-aware cumulative sums (no groupby, no app imports).

Rows must be sorted by series (store, SKU) then date; `series_start[i]` is the row index where row i's series begins.
Trailing windows exclude the current row so a day is compared with its own recent past. This module is copied verbatim
into every model bundle, so it must stay self-contained (numpy only).
"""
from __future__ import annotations

import numpy as np

# Detection features: deviations scaled so that ordinary days have light tails (Poisson / binomial z-scores against
# each store's own habits, variance normalised by the series' own count noise). These are what the models see.
DETECT_FEATURES = [
    "shrinkage_pct",
    "variance_z_series",
    "shrink_sum_7_z",
    "shrink_pct_7",
    "reversal_index",
    "velocity_z",
    "zero_sales_streak",
    "receiving_gap_units",
    "received_vs_typical",
    "adjustment_vs_typical",
    "returns_z",
    "manual_entry_z",
    "void_z",
    "override_z",
    "after_hours_z",
    "store_day_shrink_z",
]
# Context features: describe the item/day (useful for explanations and the drill-down, not for scoring).
CONTEXT_FEATURES = ["variance_units", "variance_value", "sold_units", "stock_cover_days", "is_delivery_day", "on_promo", "log_unit_cost"]
NUMERIC_FEATURES = DETECT_FEATURES + CONTEXT_FEATURES
CATEGORICAL_FEATURES = ["dow", "category"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
BASELINE_FEATURES = ["shrinkage_pct", "variance_units", "category"]

# raw columns each feature needs (used to drop features when an upload lacks a column)
NEEDS = {
    "receiving_gap_units": ["receiving_scans"],
    "manual_entry_z": ["manual_entry_scans", "pos_scans"],
    "void_z": ["void_count", "pos_scans"],
    "override_z": ["override_count", "pos_scans"],
    "after_hours_z": ["after_hours_scans"],
    "returns_z": ["returned_units"],
    "on_promo": ["on_promo"],
}


def slog(x: np.ndarray) -> np.ndarray:
    return (np.sign(x) * np.log1p(np.abs(x))).astype(np.float32)


def series_starts(series_id: np.ndarray) -> np.ndarray:
    """Row index of the first row of each row's series (series_id sorted/contiguous)."""
    n = len(series_id)
    pos = np.arange(n)
    is_start = np.r_[True, series_id[1:] != series_id[:-1]]
    return np.maximum.accumulate(np.where(is_start, pos, 0))


class _Roll:
    """Trailing-window statistics over contiguous series."""

    def __init__(self, start: np.ndarray) -> None:
        self.start = start
        self.pos = np.arange(len(start))

    def _sum(self, x: np.ndarray, w: int, include_current: bool) -> tuple[np.ndarray, np.ndarray]:
        cs = np.concatenate(([0.0], np.cumsum(x, dtype=np.float64)))
        end = self.pos + (1 if include_current else 0)
        lo = np.maximum(end - w, self.start)
        cnt = (end - lo).astype(np.float64)
        return cs[end] - cs[lo], cnt

    def mean(self, x: np.ndarray, w: int, include_current: bool = False, empty: float = 0.0) -> np.ndarray:
        s, c = self._sum(x, w, include_current)
        return np.where(c > 0, s / np.maximum(c, 1), empty)

    def sum(self, x: np.ndarray, w: int, include_current: bool = True) -> np.ndarray:
        return self._sum(x, w, include_current)[0]

    def std(self, x: np.ndarray, w: int, include_current: bool = False) -> np.ndarray:
        s, c = self._sum(x, w, include_current)
        s2, _ = self._sum(x.astype(np.float64) ** 2, w, include_current)
        m = np.where(c > 0, s / np.maximum(c, 1), 0.0)
        v = np.where(c > 1, s2 / np.maximum(c, 1) - m**2, 0.0)
        return np.sqrt(np.maximum(v, 0.0))


def _robust_z_by_group(values: np.ndarray, group: np.ndarray, n_groups: int) -> np.ndarray:
    """Robust z of each value against the median/MAD of its group (groups are small: one per store)."""
    out = np.zeros(len(values), dtype=np.float64)
    order = np.argsort(group, kind="stable")
    g_sorted = group[order]
    bounds = np.searchsorted(g_sorted, np.arange(n_groups + 1))
    for g in range(n_groups):
        idx = order[bounds[g] : bounds[g + 1]]
        if len(idx) == 0:
            continue
        v = values[idx]
        med = np.median(v)
        mad = np.median(np.abs(v - med)) * 1.4826 + 1e-6
        out[idx] = (v - med) / max(mad, 1.0)
    return out


def _store_rate(num: np.ndarray, den: np.ndarray, store: np.ndarray, n_stores: int) -> np.ndarray:
    tn = np.bincount(store, weights=num, minlength=n_stores)
    td = np.bincount(store, weights=den, minlength=n_stores)
    return (tn / np.maximum(td, 1.0))[store]


def global_rates(cols: dict[str, np.ndarray]) -> dict[str, float]:
    """Dataset-wide rates that chunked feature engineering must share."""
    sold = cols["sold_units"].astype(np.float64)
    promo = cols["on_promo"].astype(bool) if "on_promo" in cols else np.zeros(len(sold), dtype=bool)
    up = float(sold[promo].mean() / max(sold[~promo].mean(), 1e-6)) if promo.any() and (~promo).any() else 1.0
    ret = float(cols["returned_units"].astype(np.float64).sum() / max(sold.sum(), 1.0)) if "returned_units" in cols else 0.0
    return {"promo_uplift": up, "return_rate": ret}


def engineer(cols: dict[str, np.ndarray], start: np.ndarray, unit_cost: np.ndarray, category: np.ndarray, dow: np.ndarray, n_stores: int, n_dates: int, rates: dict[str, float] | None = None) -> dict[str, np.ndarray]:
    """Return float32 feature columns. `cols` holds raw daily columns (missing optional ones are allowed).

    `start` holds row indices local to `cols`; `rates` comes from `global_rates()` when engineering in chunks.
    """
    rates = rates or global_rates(cols)
    n = len(start)
    zeros = np.zeros(n, dtype=np.float64)
    g = lambda k: cols[k].astype(np.float64) if k in cols else zeros  # noqa: E731
    roll = _Roll(start)
    store = cols["store_code"].astype(np.int64)
    day = cols["date_idx"].astype(np.int64)
    expected, counted = g("expected_closing"), g("counted_closing")
    sold, received = g("sold_units"), g("received_units")
    pos = g("pos_scans")
    promo = g("on_promo")
    var = expected - counted  # positive = stock missing
    f: dict[str, np.ndarray] = {}
    # --- shrinkage
    f["shrinkage_pct"] = np.clip(var / np.maximum(expected, 1.0) * 100, -200, 200)
    f["variance_units"] = slog(var)
    f["variance_value"] = slog(var * unit_cost)
    m28, s28 = roll.mean(var, 28), roll.std(var, 28)
    noise = np.maximum(s28, 0.35 + 0.025 * np.maximum(counted, 0))  # never trust a tiny history-based noise level
    f["variance_z_series"] = np.clip((var - m28) / (noise + 0.5), -50, 50)
    v7 = roll.sum(var, 7, include_current=True)
    sold7 = roll.sum(sold, 7, include_current=True)
    # count noise telescopes over a window (yesterday's error is reversed today), so a 7-day sum keeps genuine loss
    f["shrink_sum_7_z"] = np.clip(v7 / (noise * 1.2 + 0.7), -50, 50)
    f["shrink_pct_7"] = np.clip(v7 / np.maximum(sold7 + counted, 1.0) * 100, -200, 200)
    prev_var = np.where(np.arange(n) > start, np.r_[0.0, var[:-1]], 0.0)
    f["reversal_index"] = np.clip(np.sqrt(np.maximum(0.0, -prev_var * var)) / (noise + 0.5), 0, 50)
    # --- sales velocity (promotions are expected uplifts, not anomalies)
    off = promo == 0
    uplift = rates["promo_uplift"]
    base28 = roll.mean(np.where(off, sold, sold / max(uplift, 1e-6)), 28)
    exp_sold = base28 * np.where(off, 1.0, uplift)
    f["velocity_z"] = np.clip((sold - exp_sold) / np.sqrt(exp_sold + 1.0), -20, 20)
    zero_day = (sold == 0) & (counted > 0)
    p_ = np.arange(n)
    last = np.maximum.accumulate(np.maximum(np.where(~zero_day, p_, -1), start - 1))
    streak = (p_ - last).astype(np.float64)
    # expected units missed during a run of zero-sale days = -log P(run) under Poisson demand
    f["zero_sales_streak"] = np.clip(streak * base28, 0, 200)
    f["sold_units"] = slog(sold)
    f["stock_cover_days"] = slog(counted / (base28 + 0.1))
    # --- receiving and bookkeeping
    deliv = (received > 0).astype(np.float64)
    rec_typ = roll.sum(received, 28, include_current=False) / np.maximum(roll.sum(deliv, 28, include_current=False), 1.0)
    f["received_vs_typical"] = np.where(received > 0, slog(received / (rec_typ + 1.0)), 0.0)
    f["receiving_gap_units"] = slog(received - g("receiving_scans")) if "receiving_scans" in cols else zeros
    f["is_delivery_day"] = deliv
    adj = np.abs(g("adjustment_units"))
    f["adjustment_vs_typical"] = slog(adj / (roll.mean(adj, 28) + 1.0))
    # --- till and scan behaviour against each store's own habits
    ret = g("returned_units")
    ret_rate = rates["return_rate"]
    exp_ret = ret_rate * np.maximum(base28, sold)
    f["returns_z"] = np.clip((ret - exp_ret) / np.sqrt(exp_ret + 0.5), -10, 50)
    man = g("manual_entry_scans")
    r = _store_rate(man, pos, store, n_stores)
    f["manual_entry_z"] = np.clip((man - pos * r) / np.sqrt(pos * r * (1 - r) + 0.5), -10, 50)
    vd = g("void_count")
    r = _store_rate(vd, pos + 1.0, store, n_stores)
    exp_v = r * (pos + 1.0)
    f["void_z"] = np.clip((vd - exp_v) / np.sqrt(exp_v + 0.5), -10, 50)
    ov = g("override_count")
    r = _store_rate(ov, pos + 1.0, store, n_stores)
    exp_o = r * (pos + 1.0)
    f["override_z"] = np.clip((ov - exp_o) / np.sqrt(exp_o + 0.5), -10, 50)
    ah = g("after_hours_scans")
    mu = _store_rate(ah, np.ones(n), store, n_stores)
    f["after_hours_z"] = np.clip((ah - mu) / np.sqrt(mu + 0.5), -10, 50)
    # --- store-level shrink that day (several SKUs at once is a classic internal-theft signature)
    key = store * n_dates + day
    shrink_val = np.maximum(var, 0) * unit_cost
    tot = np.bincount(key, weights=shrink_val, minlength=n_stores * n_dates)
    z = _robust_z_by_group(tot, np.repeat(np.arange(n_stores), n_dates), n_stores)
    f["store_day_shrink_z"] = np.clip(z[key], -10, 50)
    f["on_promo"] = promo
    f["log_unit_cost"] = np.log1p(unit_cost)
    f["dow"] = dow.astype(np.float64)
    f["category"] = category.astype(np.float64)
    out = {}
    for k in FEATURES:
        a = np.asarray(f[k], dtype=np.float32)
        out[k] = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
    return out


def matrix(features: dict[str, np.ndarray], names: list[str], rows: np.ndarray | slice | None = None) -> np.ndarray:
    """Stack feature columns (optionally a row subset) into a float32 matrix in `names` order."""
    if rows is None:
        rows = slice(None)
    return np.column_stack([np.asarray(features[k][rows], dtype=np.float32) for k in names])
