"""Why a day was flagged (plain sentences) and the most likely kind of problem behind an incident."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.services import features as F


def baseline(feat_rows: dict[str, np.ndarray], categories: np.ndarray, cat_names: list[str]) -> dict[str, Any]:
    """Median and robust spread of each detection feature, overall and per category (from a training sample)."""
    def stats(mask: np.ndarray | None) -> dict[str, list[float]]:
        out = {}
        for f in F.DETECT_FEATURES:
            v = feat_rows[f] if mask is None else feat_rows[f][mask]
            if len(v) == 0:
                continue
            med = float(np.median(v))
            mad = float(np.median(np.abs(v - med)) * 1.4826)
            q99 = float(np.quantile(v, 0.99))
            out[f] = [round(med, 4), round(max(mad, 0.05), 4), round(q99, 4)]
        return out

    by_cat = {}
    for i, c in enumerate(cat_names):
        m = categories == i
        if m.sum() >= 200:
            by_cat[c] = stats(m)
    return {"global": stats(None), "by_category": by_cat}


def deviations(row: dict[str, float], base: dict[str, Any], category: str) -> dict[str, float]:
    ref = base.get("by_category", {}).get(category) or base.get("global", {})
    glob = base.get("global", {})
    out = {}
    for f in F.DETECT_FEATURES:
        med, mad, q99 = (ref.get(f) or glob.get(f) or [0.0, 1.0, 1.0])
        x = float(row.get(f, 0.0))
        # scale by the larger of the robust spread and a share of the 99th percentile so near-constant features stay calm
        spread = max(mad, abs(q99 - med) / 3.0, 0.05)
        out[f] = (x - med) / spread
    return out


def _fmt_int(v: Any) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v)


def reasons(feat: dict[str, float], raw: dict[str, Any], base: dict[str, Any], category: str, top: int = 3, ae_errors: dict[str, float] | None = None) -> list[str]:
    dev = deviations(feat, base, category)
    if ae_errors:
        for f, e in ae_errors.items():
            dev[f] = max(dev.get(f, 0.0), e)
    var = int(raw.get("expected_closing", 0)) - int(raw.get("counted_closing", 0))
    sold, rec = raw.get("sold_units", 0), raw.get("received_units", 0)
    texts = {
        "shrinkage_pct": f"Shrinkage {feat.get('shrinkage_pct', 0):.0f}% of expected stock ({_fmt_int(var)} units missing), unusual for {category}",
        "variance_z_series": f"Stock gap of {_fmt_int(var)} units is far outside this item's normal day-to-day noise",
        "shrink_sum_7_z": f"Stock has kept going missing: {feat.get('shrink_pct_7', 0):.0f}% over the last 7 days, well beyond count noise",
        "shrink_pct_7": f"Shrinkage over the last 7 days is {feat.get('shrink_pct_7', 0):.0f}%",
        "reversal_index": f"Today's gap ({_fmt_int(var)} units) reverses yesterday's: the pattern of a miscount",
        "velocity_z": (f"Sold {_fmt_int(sold)} units, far more than normal without a promotion" if feat.get("velocity_z", 0) > 0 else f"Sold {_fmt_int(sold)} units, far fewer than normal"),
        "zero_sales_streak": f"No sales for several days although the books show {_fmt_int(raw.get('counted_closing', 0))} units in stock",
        "receiving_gap_units": f"Delivery booked as {_fmt_int(rec)} units but {_fmt_int(raw.get('receiving_scans', 0))} were scanned in",
        "received_vs_typical": f"Delivery of {_fmt_int(rec)} units is many times the usual size for this item",
        "adjustment_vs_typical": f"Recorded adjustment of {_fmt_int(raw.get('adjustment_units', 0))} units is far larger than usual",
        "returns_z": f"{_fmt_int(raw.get('returned_units', 0))} returns recorded, far more than this item normally gets",
        "manual_entry_z": f"{_fmt_int(raw.get('manual_entry_scans', 0))} of {_fmt_int(raw.get('pos_scans', 0))} scans keyed in by hand, unusual for this store",
        "void_z": f"{_fmt_int(raw.get('void_count', 0))} voided till lines, well above the store's habit",
        "override_z": f"{_fmt_int(raw.get('override_count', 0))} price or quantity overrides at the till",
        "after_hours_z": f"{_fmt_int(raw.get('after_hours_scans', 0))} scans outside opening hours",
        "store_day_shrink_z": "Several items went missing in this store on the same day",
    }
    ranked = sorted(dev.items(), key=lambda kv: -kv[1])
    out, used = [], set()
    for f, z in ranked:
        if z < 2.0 or len(out) >= top:
            break
        # avoid three variants of the same shrinkage story
        group = "shrink" if f in ("shrinkage_pct", "variance_z_series", "shrink_pct_7") else f
        if group in used:
            continue
        used.add(group)
        out.append(texts.get(f, f))
    return out or ["A combination of small deviations across several signals"]


def guess_type(peak: dict[str, float], n_days: int, net_var: float, abs_var: float, delivery: bool) -> tuple[str, float]:
    """Ordered rules over the incident's peak day; returns (type, confidence 0-1)."""
    g = lambda k: float(peak.get(k, 0.0))  # noqa: E731
    if g("received_vs_typical") >= 1.8 or g("adjustment_vs_typical") >= 1.8:
        return "data_entry_error", 0.85 if n_days <= 3 else 0.6
    if g("reversal_index") >= 3 or (n_days <= 2 and abs_var >= 4 and abs(net_var) <= 0.3 * abs_var):
        return "counting_error", 0.75
    if delivery and abs(g("receiving_gap_units")) >= 1.0:
        return "receiving_error", 0.75
    if max(g("void_z"), g("override_z"), g("manual_entry_z"), g("returns_z")) >= 3:
        return "scan_fraud", 0.7
    if g("after_hours_z") >= 3 or g("store_day_shrink_z") >= 3:
        return "theft_internal", 0.65
    if (abs(g("velocity_z")) >= 4 or g("zero_sales_streak") >= 6) and abs(net_var) < 3:
        return "velocity_shift", 0.6
    if g("shrink_sum_7_z") >= 3 or (net_var >= 3 and n_days >= 2):
        return "theft_external", 0.55
    return "unclear", 0.3
