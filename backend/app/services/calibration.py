"""P(true anomaly | score percentile): binned rates with a Beta(1,1) prior, made monotone with pool-adjacent-violators.

Pure numpy (scikit-learn's isotonic regression pulls in scipy.interpolate, which is not always loadable here).
"""
from __future__ import annotations

import numpy as np

from app.schemas import Calibration


def _edges(lo: float, bins: int) -> np.ndarray:
    """Bin edges in percentile space, denser near the top (tail = 1 - percentile, geometric)."""
    tail_hi = max(1.0 - lo, 1e-4)
    tails = np.geomspace(tail_hi, 1e-5, bins)
    return np.r_[1.0 - tails, 1.0]


def pav(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted pool-adjacent-violators: the non-decreasing sequence closest to y."""
    vals, wts, sizes = [], [], []
    for yi, wi in zip(y.astype(float), w.astype(float)):
        vals.append(yi)
        wts.append(wi)
        sizes.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            tw = wts[-2] + wts[-1]
            v = (vals[-2] * wts[-2] + vals[-1] * wts[-1]) / max(tw, 1e-12)
            s = sizes[-2] + sizes[-1]
            vals[-2:], wts[-2:], sizes[-2:] = [v], [tw], [s]
    return np.repeat(vals, sizes)


def fit(percentile: np.ndarray, label: np.ndarray, weight: np.ndarray | None, lo: float, source: str, note: str, bins: int = 16) -> Calibration:
    percentile = np.asarray(percentile, dtype=np.float64)
    label = np.asarray(label, dtype=np.float64)
    weight = np.ones_like(label) if weight is None else np.asarray(weight, dtype=np.float64)
    edges = _edges(lo, bins)
    k = np.clip(np.searchsorted(edges, percentile, side="right") - 1, 0, bins - 1)
    above = percentile >= edges[0]
    pos = np.bincount(k[above], weights=(label * weight)[above], minlength=bins)
    tot = np.bincount(k[above], weights=weight[above], minlength=bins)
    # weights can be large (sampled negatives); the prior is applied on an effective count scale
    scale = np.where(tot > 0, np.bincount(k[above], minlength=bins) / np.maximum(tot, 1e-12), 1.0)
    p = (pos * scale + 1.0) / (tot * scale + 2.0)
    p = pav(p, np.maximum(tot * scale, 1.0))
    return Calibration(source=source, note=note, percentiles=[round(float(e), 6) for e in edges[:-1]], p_true=[round(float(x), 4) for x in p])  # type: ignore[arg-type]


def prior(lo: float, bins: int = 16) -> Calibration:
    edges = _edges(lo, bins)
    p = np.linspace(0.15, 0.6, bins)
    return Calibration(source="prior", note="Assumption: no labels yet; 15% of alerts at the threshold are real, rising to 60% at the very top.", percentiles=[round(float(e), 6) for e in edges[:-1]], p_true=[round(float(x), 4) for x in p])


def predict(cal: Calibration, percentile: np.ndarray) -> np.ndarray:
    if not cal.p_true:
        return np.full(len(np.atleast_1d(percentile)), 0.3)
    edges = np.asarray(cal.percentiles)
    k = np.clip(np.searchsorted(edges, np.asarray(percentile), side="right") - 1, 0, len(cal.p_true) - 1)
    return np.asarray(cal.p_true)[k]
