"""Filters for the assistant's tools: region, store, category, team and period, resolved from the user's loose wording.

The model says "london", "the Leeds store", "Beauty" or "last 30 days"; the tools need exact values. resolve() matches
case-insensitively (ids, names, plurals, unique partial matches), accepts comma-separated lists, and when nothing matches
returns an error that lists the valid values so the model can retry or ask instead of guessing.

Periods count back from the data's last day (as on the Executive overview), not from today: a snapshot can end days or
weeks before today. An alert belongs to the period it started in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.services import storage
from app.services.detection import scope_mask


PERIOD_RULE = "Periods count back from the data's last day (not from today); an alert counts in the period it started in."


class ScopeError(ValueError):
    pass


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _stem(s: str) -> str:
    return s[:-1] if len(s) > 3 and s.endswith("s") else s


def _split(v: str | list[str] | None) -> list[str]:
    if v is None:
        return []
    items = v if isinstance(v, list) else str(v).split(",")
    return [str(x).strip() for x in items if str(x).strip()]


def _match_one(term: str, options: list[tuple[str, list[str]]]) -> list[str]:
    """options: (value, [names it can be called]). Exact, then plural-insensitive, then unique partial match."""
    t = _norm(term)
    for strict in (lambda n: n == t, lambda n: _stem(n) == _stem(t)):
        hit = [v for v, names in options if any(strict(_norm(n)) for n in names)]
        if hit:
            return list(dict.fromkeys(hit))
    if len(t) >= 3:
        hit = [v for v, names in options if any(t in _norm(n) or (len(_norm(n)) >= 3 and _norm(n) in t) for n in names)]
        return list(dict.fromkeys(hit))
    return []


def resolve(value: str | list[str] | None, options: list[tuple[str, list[str]]], what: str, show: list[str]) -> list[str] | None:
    terms = _split(value)
    if not terms or any(_norm(t) in ("all", "any", "every", "allregions", "allstores", "allcategories") for t in terms):
        return None
    out: list[str] = []
    for term in terms:
        hit = _match_one(term, options)
        if not hit:
            raise ScopeError(f"No {what} matches '{term}'. Valid {what} values: {', '.join(show[:40])}{' ...' if len(show) > 40 else ''}.")
        if len(hit) > 3:
            raise ScopeError(f"'{term}' matches {len(hit)} {what} values ({', '.join(hit[:8])}...); ask the user which one.")
        out += hit
    return list(dict.fromkeys(out))


def _iso(v: str | None, label: str) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except ValueError as exc:
        raise ScopeError(f"{label} must be a date like 2026-09-30, not '{v}'.") from exc


@dataclass
class Scope:
    regions: list[str] | None = None
    store_ids: list[str] | None = None
    categories: list[str] | None = None
    teams: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    data_start: str = ""
    data_end: str = ""
    store_names: dict[str, str] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return bool(self.regions or self.store_ids or self.categories or self.teams or self.date_from or self.date_to)

    @property
    def place_active(self) -> bool:
        return bool(self.regions or self.store_ids or self.categories or self.teams)

    def mask(self, inc: pd.DataFrame) -> np.ndarray:
        return scope_mask(inc, region=self.regions, store_id=self.store_ids, team=self.teams, category=self.categories, date_from=self.date_from, date_to=self.date_to)

    def describe(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.regions:
            d["regions"] = self.regions
        if self.store_ids:
            d["stores"] = [f"{s} {self.store_names.get(s, '')}".strip() for s in self.store_ids]
        if self.categories:
            d["categories"] = self.categories
        if self.teams:
            d["teams"] = self.teams
        d["period"] = f"{self.date_from or self.data_start} to {self.date_to or self.data_end}"
        if not self.date_from and not self.date_to:
            d["period"] += " (all data)"
        d["data_covers"] = f"{self.data_start} to {self.data_end}"
        if self.date_from or self.date_to:
            d["period_rule"] = PERIOD_RULE
        return d


def options(ds: storage.Dataset) -> dict[str, list[tuple[str, list[str]]]]:
    st, sk = ds.stores, ds.skus
    regions = sorted(st["region"].dropna().astype(str).unique().tolist()) if "region" in st else []
    teams = sorted(st["warehouse_team"].dropna().astype(str).unique().tolist()) if "warehouse_team" in st else []
    cats = sorted(sk["category"].dropna().astype(str).unique().tolist())
    stores = [(str(r.store_id), [str(r.store_id), str(r.store_name)]) for r in st.itertuples()]
    return {"region": [(r, [r]) for r in regions], "team": [(t, [t]) for t in teams], "category": [(c, [c]) for c in cats], "store": stores}


def build(ds: storage.Dataset, *, days: int | None = None, start_date: str | None = None, end_date: str | None = None, region: Any = None, store: Any = None, category: Any = None, team: Any = None) -> Scope:
    """Raise ScopeError with a usable message when a value does not match the data."""
    opt = options(ds)
    first, last = date.fromisoformat(str(ds.dates[0])), date.fromisoformat(str(ds.dates[-1]))
    sc = Scope(data_start=first.isoformat(), data_end=last.isoformat(), store_names={str(r.store_id): str(r.store_name) for r in ds.stores.itertuples()})
    sc.regions = resolve(region, opt["region"], "region", [v for v, _ in opt["region"]]) if opt["region"] or region else None
    sc.store_ids = resolve(store, opt["store"], "store", [f"{v} {n[1]}" for v, n in opt["store"]])
    sc.categories = resolve(category, opt["category"], "category", [v for v, _ in opt["category"]])
    sc.teams = resolve(team, opt["team"], "team", [v for v, _ in opt["team"]]) if opt["team"] or team else None
    lo, hi = _iso(start_date, "start_date"), _iso(end_date, "end_date")
    n = int(days or 0)
    if n < 0:
        raise ScopeError("days must be 0 (all data) or a positive number of days.")
    if n and not lo:
        end = hi or last
        lo = end - timedelta(days=n - 1)
    if lo and hi and lo > hi:
        raise ScopeError(f"start_date {lo} is after end_date {hi}.")
    if (lo and lo > last) or (hi and hi < first):
        raise ScopeError(f"The data covers {first} to {last}; the period asked for is outside it.")
    sc.date_from = max(lo, first).isoformat() if lo and lo > first else None
    sc.date_to = hi.isoformat() if hi and hi < last else None
    return sc


def top(df: pd.DataFrame, col: str, label_col: str | None = None, n: int = 10) -> list[dict[str, Any]]:
    """Same shape as the run aggregates (detection.aggregates.top), for a filtered set of alerts."""
    if not len(df) or col not in df:
        return []
    keys = [col] + ([label_col] if label_col else [])
    g = df.groupby(keys).agg(alerts=("alert_id", "size"), value=("value_at_risk_gbp", "sum"), critical=("severity", lambda x: int((x == "critical").sum()))).reset_index().sort_values("value", ascending=False).head(n)
    return [{"key": str(r[col]), "label": str(r[label_col]) if label_col else str(r[col]), "alerts": int(r["alerts"]), "value_gbp": round(float(r["value"]), 2), "critical": int(r["critical"])} for _, r in g.iterrows()]


def row_mask(ds: storage.Dataset, sc: Scope) -> np.ndarray:
    """Daily rows (store x SKU x day) inside the scope, for day-level trends."""
    m = np.ones(len(ds.daily["date_idx"]), dtype=bool)
    st = ds.stores
    if sc.regions or sc.store_ids or sc.teams:
        ok = np.ones(len(st), dtype=bool)
        if sc.regions:
            ok &= st["region"].astype(str).isin(sc.regions).to_numpy()
        if sc.store_ids:
            ok &= st["store_id"].astype(str).isin(sc.store_ids).to_numpy()
        if sc.teams:
            ok &= st["warehouse_team"].astype(str).isin(sc.teams).to_numpy()
        m &= ok[np.asarray(ds.daily["store_code"]).astype(np.int64)]
    if sc.categories:
        m &= ds.skus["category"].astype(str).isin(sc.categories).to_numpy()[np.asarray(ds.daily["sku_code"]).astype(np.int64)]
    return m
