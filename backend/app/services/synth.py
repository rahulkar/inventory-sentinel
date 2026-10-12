"""Synthetic store x SKU x day inventory simulator with injected, labelled anomalies.

Each series (one SKU in one store) carries a *physical* stock that the business cannot see and a *book* stock that the
system computes. Every evening the stock is counted (RFID-style) and the count resets the book for the next morning, so
the daily variance `expected_closing - counted_closing` is the shrinkage signal the detectors look at.

Anomalies are planned per block of stores as small event tables and applied inside the day loop. The answer key
(`truth_type`, `truth_incident`, `truth_loss_units`) is written next to the data but is never a model feature.
Hard negatives (promotions, delivery-day noise, new lines, stock-scaled count noise, background shrink) make a naive
rule of thumb raise false alarms that the learned methods avoid.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from app import config
from app.services import colstore

TYPE_CODE = {name: i for i, name in enumerate(config.ANOMALY_TYPES)}

DAILY_SPECS: dict[str, Any] = {
    "date_idx": np.int16,
    "store_code": np.int16,
    "sku_code": np.int16,
    "opening_stock": np.int32,
    "received_units": np.int16,
    "sold_units": np.int16,
    "returned_units": np.int16,
    "transfer_in_units": np.int16,
    "transfer_out_units": np.int16,
    "adjustment_units": np.int16,
    "expected_closing": np.int32,
    "counted_closing": np.int32,
    "pos_scans": np.int16,
    "manual_entry_scans": np.int16,
    "void_count": np.int16,
    "override_count": np.int16,
    "after_hours_scans": np.int16,
    "receiving_scans": np.int16,
    "on_promo": np.int8,
}
TRUTH_SPECS: dict[str, Any] = {"truth_type": np.int8, "truth_incident": np.int32, "truth_loss_units": np.int16}

# incidents per 1M rows (scaled by size and anomaly_multiplier)
RATES = {
    "theft_external": 260,
    "theft_internal": 50,  # store-nights, each hitting 3-8 SKUs
    "scan_fraud": 100,
    "counting_error": 800,
    "receiving_error": 300,
    "data_entry_error": 300,
    "velocity_shift": 120,
}


@dataclass
class GenParams:
    n_stores: int
    n_skus: int
    n_days: int
    seed: int = 42
    anomaly_multiplier: float = 1.0
    lp_coverage: float = 0.4

    @property
    def n_rows(self) -> int:
        return self.n_stores * self.n_skus * self.n_days

    @property
    def test_from_idx(self) -> int:
        return int(round(self.n_days * (1 - config.TEST_WINDOW_SHARE)))


# ---------------------------------------------------------------- dimension tables
def make_stores(p: GenParams, rng: np.random.Generator) -> pd.DataFrame:
    n = p.n_stores
    regions = rng.choice(config.REGIONS, size=n, p=config.REGION_WEIGHTS)
    names, used = [], {}
    for r in regions:
        towns = config.TOWNS[r]
        k = used.get(r, 0)
        used[r] = k + 1
        town = towns[k % len(towns)] + ("" if k < len(towns) else f" {k // len(towns) + 1}")
        names.append(town)
    fmt = rng.choice(config.STORE_FORMATS, size=n, p=[0.45, 0.3, 0.1, 0.15])
    footfall = np.round(np.clip(rng.lognormal(0.0, 0.3, n) * np.where(fmt == "flagship", 1.6, 1.0), 0.45, 2.6), 2)
    n_teams = max(2, min(8, n // 10 or 2))
    order = np.argsort(regions, kind="stable")
    team = np.empty(n, dtype=object)
    for rank, idx in enumerate(order):
        team[idx] = rank * n_teams // n
    team_names = []
    for t in range(n_teams):
        members = [regions[i] for i in range(n) if team[i] == t]
        lead = max(set(members), key=members.count) if members else "Team"
        team_names.append(f"{lead} {t + 1}")
    hotspot = (rng.random(n) < 0.2).astype(np.int8)
    return pd.DataFrame(
        {
            "store_id": [f"S{i + 1:03d}" for i in range(n)],
            "store_name": [f"Store {i + 1:03d} · {names[i]}" for i in range(n)],
            "region": regions,
            "format": fmt,
            "size_band": np.where(footfall > 1.3, "large", np.where(footfall > 0.85, "medium", "small")),
            "warehouse_team": [team_names[int(t)] for t in team],
            "footfall_index": footfall,
            "opens_at": "08:00",
            "closes_at": np.where(fmt == "flagship", "21:00", "20:00"),
            "_hotspot": hotspot,
        }
    )


def make_skus(p: GenParams, rng: np.random.Generator) -> pd.DataFrame:
    n = p.n_skus
    cats = rng.choice(config.CATEGORIES, size=n, p=config.CATEGORY_SHARE)
    med = np.array([config.CATEGORY_COST[c] for c in cats])
    cost = np.round(np.clip(rng.lognormal(np.log(med), 0.45), 0.8, 30.0), 2)
    price = np.round(cost * rng.uniform(2.2, 3.0, n), 2)
    high_risk = np.isin(cats, ["beauty", "accessories"]) | ((cats == "footwear") & (cost >= np.quantile(cost[cats == "footwear"], 0.7) if (cats == "footwear").any() else False))
    adjectives = ["Classic", "Essential", "Soft", "Printed", "Ribbed", "Cotton", "Relaxed", "Slim", "Cosy", "Everyday", "Party", "Denim"]
    nouns = {
        "womenswear": ["Dress", "Blouse", "Jeans", "Cardigan", "Skirt", "Top"],
        "menswear": ["Shirt", "Chinos", "Hoodie", "Jacket", "Polo", "Jumper"],
        "kidswear": ["Kids T-shirt", "Kids Joggers", "Baby Bodysuit", "Kids Coat", "School Shirt"],
        "footwear": ["Trainers", "Boots", "Sandals", "Slippers", "Loafers"],
        "accessories": ["Scarf", "Belt", "Earrings", "Bag", "Sunglasses", "Hat"],
        "beauty": ["Lipstick", "Mascara", "Face Serum", "Nail Polish", "Fragrance", "Brush Set"],
        "home": ["Cushion", "Throw", "Candle", "Towel", "Mug Set", "Frame"],
        "nightwear": ["Pyjama Set", "Robe", "Socks 5pk", "Lounge Pants"],
    }
    names = [f"{adjectives[i % len(adjectives)]} {rng.choice(nouns[c])}" for i, c in enumerate(cats)]
    popularity = np.round(np.clip(rng.lognormal(0.0, 0.75, n), 0.12, 9.0), 3)
    new_line = (rng.random(n) < 0.05).astype(np.int8)
    return pd.DataFrame(
        {
            "sku_id": [f"K{i + 1:05d}" for i in range(n)],
            "sku_name": names,
            "category": cats,
            "unit_cost": cost,
            "unit_price": price,
            "high_theft_risk": high_risk.astype(np.int8),
            "security_tagged": (high_risk & (rng.random(n) < 0.5)).astype(np.int8),
            "_popularity": popularity,
            "_new_line": new_line,
        }
    )


# ---------------------------------------------------------------- the simulator
class _Block:
    """Plans and applies anomaly events for one block of stores (S = stores_in_block x n_skus series)."""

    def __init__(self, p: GenParams, stores: pd.DataFrame, skus: pd.DataFrame, store_lo: int, store_hi: int, rng: np.random.Generator, incident_base: int) -> None:
        self.p, self.rng = p, rng
        nb = store_hi - store_lo
        self.nb = nb
        self.S = nb * p.n_skus
        self.store_of = np.repeat(np.arange(store_lo, store_hi), p.n_skus)  # global store code per series
        self.sku_of = np.tile(np.arange(p.n_skus), nb)
        T, S = p.n_days, self.S
        self.T = T
        f = lambda dtype=np.float32: np.zeros((T, S), dtype=dtype)  # noqa: E731
        self.extra_loss = f()  # physical units leaving unrecorded
        self.refund_extra = f()  # recorded returns with nothing physical
        self.after_hours_extra = f()
        self.void_extra = f()
        self.manual_share_extra = f()
        self.override_extra = f()
        self.lambda_mult = np.ones((T, S), dtype=np.float32)
        self.count_err = f()  # fraction under-counted on day t (reverses next day)
        self.recv_err = f()  # signed fraction of delivery physically missing (+) or extra (-)
        self.recv_scan_shows = np.zeros((T, S), dtype=bool)
        self.entry_err = np.zeros((T, S), dtype=np.int8)  # 1 = data-entry error planned
        self.ev_type = np.zeros((T, S), dtype=np.int8)
        self.ev_incident = np.zeros((T, S), dtype=np.int32)
        self.next_incident = incident_base
        self.store_df = stores
        self.sku_df = skus
        self.busy_ = (skus["_popularity"].to_numpy()[self.sku_of] * stores["footfall_index"].to_numpy()[self.store_of]) >= 1.5
        self._plan()

    # -------- helpers
    def _n_events(self, kind: str) -> int:
        expect = RATES[kind] * self.p.anomaly_multiplier * (self.S * self.T) / 1_000_000
        return int(self.rng.poisson(expect))

    def _new_incident(self) -> int:
        self.next_incident += 1
        return self.next_incident

    def _series_weights(self, theft: bool) -> np.ndarray:
        w = np.ones(self.S)
        if theft:
            w *= np.where(self.sku_df["high_theft_risk"].to_numpy()[self.sku_of] == 1, 4.0, 1.0)
            w *= np.where(self.store_df["_hotspot"].to_numpy()[self.store_of] == 1, 3.0, 1.0)
        return w / w.sum()

    def _mark(self, t0: int, t1: int, s: int | np.ndarray, kind: str) -> int:
        inc = self._new_incident()
        self.ev_type[t0:t1, s] = np.where(self.ev_type[t0:t1, s] == 0, -TYPE_CODE[kind], self.ev_type[t0:t1, s])
        self.ev_incident[t0:t1, s] = np.where(self.ev_incident[t0:t1, s] == 0, inc, self.ev_incident[t0:t1, s])
        return inc

    # -------- planning
    def _plan(self) -> None:
        rng, T, S = self.rng, self.T, self.S
        start_min = 3  # leave a few days of history at the start
        # 1 external theft
        for s in rng.choice(S, size=self._n_events("theft_external"), p=self._series_weights(True)):
            d = int(rng.integers(3, 11))
            t0 = int(rng.integers(start_min, max(start_min + 1, T - d)))
            t1 = min(T, t0 + d)
            self.extra_loss[t0:t1, s] += rng.uniform(1.0, 4.0)  # base units/day (scaled with sales at runtime)
            self._mark(t0, t1, s, "theft_external")
        # 2 internal theft: one store-night hits several SKUs
        sku_value = self.sku_df["unit_cost"].to_numpy()
        for _ in range(self._n_events("theft_internal")):
            b = int(rng.integers(0, self.nb))
            k = int(rng.integers(3, 9))
            pref = sku_value / sku_value.sum()
            skus = rng.choice(self.p.n_skus, size=k, replace=False, p=pref)
            series = b * self.p.n_skus + skus
            nights = int(rng.integers(1, 5))
            t0 = int(rng.integers(start_min, T - nights))
            t1 = t0 + nights
            inc = self._new_incident()
            for s in series:
                self.extra_loss[t0:t1, s] += rng.uniform(2.0, 8.0)
                self.after_hours_extra[t0:t1, s] += rng.integers(3, 11)
                self.ev_type[t0:t1, s] = np.where(self.ev_type[t0:t1, s] == 0, -TYPE_CODE["theft_internal"], self.ev_type[t0:t1, s])
                self.ev_incident[t0:t1, s] = np.where(self.ev_incident[t0:t1, s] == 0, inc, self.ev_incident[t0:t1, s])
        # 3 scan fraud (sweethearting or refund fraud)
        for s in rng.choice(S, size=self._n_events("scan_fraud"), p=self._series_weights(True)):
            d = int(rng.integers(3, 9))
            t0 = int(rng.integers(start_min, T - d))
            t1 = t0 + d
            if rng.random() < 0.6:
                self.extra_loss[t0:t1, s] += rng.uniform(1.0, 3.0)
                self.void_extra[t0:t1, s] += rng.integers(2, 7)
                self.manual_share_extra[t0:t1, s] += rng.uniform(0.2, 0.4)
                self.override_extra[t0:t1, s] += rng.integers(1, 4)
            else:
                self.refund_extra[t0:t1, s] += rng.integers(2, 7)
                self.override_extra[t0:t1, s] += rng.integers(1, 3)
            self._mark(t0, t1, s, "scan_fraud")
        # 4 counting errors (reverse the next day)
        for s in rng.integers(0, S, self._n_events("counting_error")):
            t0 = int(rng.integers(start_min, T - 1))
            self.count_err[t0, s] = rng.uniform(0.05, 0.40)
            self._mark(t0, t0 + 2, s, "counting_error")
        # 5 receiving errors (applied on the next delivery day at runtime)
        for s in rng.integers(0, S, self._n_events("receiving_error")):
            t0 = int(rng.integers(start_min, T - 1))
            frac = rng.uniform(0.10, 0.50) * (1 if rng.random() < 0.7 else -1)
            self.recv_err[t0, s] = frac
            self.recv_scan_shows[t0, s] = rng.random() < 0.7
        # 6 data-entry errors
        for s in rng.integers(0, S, self._n_events("data_entry_error")):
            t0 = int(rng.integers(start_min, T))
            self.entry_err[t0, s] = 1
        # 7 velocity shifts (phantom stock or unexplained spike) on items that normally sell every day
        busy = np.flatnonzero(self.busy_)
        for s in (rng.choice(busy, size=self._n_events("velocity_shift")) if len(busy) else []):
            d = int(rng.integers(5, 13))
            t0 = int(rng.integers(start_min + 7, max(start_min + 8, T - d)))
            t1 = min(T, t0 + d)
            self.lambda_mult[t0:t1, s] = 0.02 if rng.random() < 0.7 else rng.uniform(3.0, 5.0)
            self._mark(t0, t1, s, "velocity_shift")


def simulate_block(p: GenParams, stores: pd.DataFrame, skus: pd.DataFrame, store_lo: int, store_hi: int, rng: np.random.Generator, incident_base: int) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], int]:
    """Return (daily columns, truth columns) for stores [store_lo, store_hi), in (series, day) row order."""
    blk = _Block(p, stores, skus, store_lo, store_hi, rng, incident_base)
    T, S = blk.T, blk.S
    st, sk = blk.store_of, blk.sku_of
    footfall = stores["footfall_index"].to_numpy()[st]
    popularity = skus["_popularity"].to_numpy()[sk]
    new_line = skus["_new_line"].to_numpy()[sk] == 1
    base_lam = (popularity * footfall * rng.lognormal(0.0, 0.25, S)).astype(np.float64)
    # store habits
    store_manual = rng.uniform(0.02, 0.07, len(stores))[st]
    store_void = rng.uniform(0.01, 0.03, len(stores))[st]
    deliveries = np.zeros((len(stores), 7), dtype=bool)
    for i in range(len(stores)):
        deliveries[i, rng.choice(7, size=2, replace=False)] = True
    start_weekday = pd.Timestamp(config.SYN_START).weekday()
    dows = (start_weekday + np.arange(T)) % 7
    dow_factor = np.array([0.85, 0.85, 0.9, 0.95, 1.1, 1.35, 1.2])  # Mon..Sun
    trend = 1 + 0.15 * np.sin(np.linspace(0, 2.3, T))
    # promotions: 7-day blocks, ~5% of series-days
    promo = np.zeros((T, S), dtype=bool)
    n_promos = int(0.05 * T * S / 7)
    ps = rng.integers(0, S, n_promos)
    pt = rng.integers(0, max(1, T - 7), n_promos)
    for k in range(7):
        promo[np.minimum(pt + k, T - 1), ps] = True
    promo_mult = np.where(promo, rng.uniform(1.8, 3.0, (1, S)), 1.0)

    cover = 10.0
    target = np.ceil(base_lam * cover + 2 * np.sqrt(base_lam * cover) + 3).astype(np.int64)
    phys = target.copy()  # physical stock at start
    book_open = phys.copy()
    out = {k: np.zeros((T, S), dtype=np.int64) for k in DAILY_SPECS if k not in ("date_idx", "store_code", "sku_code")}
    truth_type = np.zeros((T, S), dtype=np.int8)
    truth_inc = np.zeros((T, S), dtype=np.int32)
    truth_loss = np.zeros((T, S), dtype=np.int32)
    prev_count_err = np.zeros(S, dtype=bool)
    for t in range(T):
        dow = dows[t]
        opening = book_open
        # deliveries on the store's two weekdays: order up to target
        is_deliv = deliveries[st, dow]
        rec = np.where(is_deliv, np.maximum(0, target - opening), 0)
        rec = np.where(rec > 0, ((rec + 3) // 4) * 4, 0)
        phys_rec = rec.copy()
        recv_scans = rec + np.where(rng.random(S) < 0.05, rng.integers(-1, 2, S), 0)
        # receiving errors land on the first delivery at/after the planned day
        pend = blk.recv_err[t] != 0
        if t > 0:
            carry = (blk.recv_err[t - 1] != 0) & (out["received_units"][t - 1] == 0)
            blk.recv_err[t] = np.where(carry & ~pend, blk.recv_err[t - 1], blk.recv_err[t])
            blk.recv_scan_shows[t] = np.where(carry & ~pend, blk.recv_scan_shows[t - 1], blk.recv_scan_shows[t])
        rerr = (blk.recv_err[t] != 0) & (rec > 0)
        if rerr.any():
            delta = np.maximum(1, np.round(np.abs(blk.recv_err[t]) * rec)).astype(np.int64) * np.sign(blk.recv_err[t]).astype(np.int64)
            phys_rec = np.where(rerr, np.maximum(0, rec - delta), phys_rec)
            recv_scans = np.where(rerr & blk.recv_scan_shows[t], phys_rec, recv_scans)
            truth_type[t] = np.where(rerr, TYPE_CODE["receiving_error"], truth_type[t])
            for s in np.flatnonzero(rerr):
                blk.next_incident += 1
                truth_inc[t, s] = blk.next_incident
            truth_loss[t] = np.where(rerr, rec - phys_rec, truth_loss[t])
        # demand
        lam = base_lam * dow_factor[dow] * trend[t] * promo_mult[t] * blk.lambda_mult[t]
        if new_line.any():
            ramp = t < 14
            lam = np.where(new_line & ramp, lam * rng.lognormal(0.0, 0.8, S), lam)
        avail = np.maximum(0, phys + phys_rec)
        sold = np.minimum(rng.poisson(lam), avail)
        # returns (genuine) and refund fraud (recorded only)
        ret_real = rng.poisson(0.035 * lam)
        refund = blk.refund_extra[t].astype(np.int64)
        returned = ret_real + refund
        # transfers and recorded write-offs (physical too)
        tr_out = np.where(rng.random(S) < 0.008, np.minimum(avail - sold, rng.integers(1, 6, S)), 0)
        tr_out = np.maximum(tr_out, 0)
        tr_in = np.where(rng.random(S) < 0.008, rng.integers(1, 6, S), 0)
        adj = np.where(rng.random(S) < 0.01, -rng.integers(1, 3, S), 0)
        # unrecorded physical loss: background shrink (unlabelled) + planned thefts
        bg = (rng.random(S) < 0.03).astype(np.int64)
        planned = blk.extra_loss[t]
        theft = np.where(planned > 0, np.maximum(np.round(planned + 0.25 * sold * rng.uniform(0.6, 1.6, S)), 1), 0).astype(np.int64)
        phys_close = avail - sold + ret_real + tr_in - tr_out + adj
        loss = np.minimum(np.maximum(phys_close, 0), bg + theft)
        phys_close = phys_close - loss
        # recorded quantities, with data-entry errors
        rec_recorded = rec.copy()
        adj_recorded = adj.copy()
        ent = blk.entry_err[t] == 1
        if ent.any():
            typed_rec = ent & (rec > 0)
            rec_recorded = np.where(typed_rec, rec * 10, rec_recorded)
            typed_adj = ent & (rec == 0)
            mag = rng.integers(20, 61, S)
            adj_recorded = np.where(typed_adj, np.where(rng.random(S) < 0.5, mag, -mag), adj_recorded)
            truth_type[t] = np.where(ent, TYPE_CODE["data_entry_error"], truth_type[t])
            for s in np.flatnonzero(ent):
                blk.next_incident += 1
                truth_inc[t, s] = blk.next_incident
        expected = opening + rec_recorded + returned + tr_in - sold - tr_out + adj_recorded
        # the evening count: noise grows with stock; new lines are noisier
        sigma = 0.35 + 0.025 * np.maximum(phys_close, 0) + np.where(new_line & (t < 14), 1.0, 0.0)
        noise = np.round(rng.normal(0, sigma)).astype(np.int64)
        counted = np.maximum(0, phys_close + noise)
        ce = blk.count_err[t] > 0
        if ce.any():
            k = np.maximum(3, np.round(blk.count_err[t] * np.maximum(phys_close, 1))).astype(np.int64)
            counted = np.where(ce, np.maximum(0, counted - k), counted)
        # scans
        pos = sold + rng.poisson(0.08 * sold)
        manual = rng.binomial(np.maximum(pos, 0), np.clip(store_manual + blk.manual_share_extra[t], 0, 0.95))
        void = rng.poisson(store_void * pos + 0.04) + blk.void_extra[t].astype(np.int64)
        overr = rng.poisson(0.01 * pos + 0.02) + blk.override_extra[t].astype(np.int64)
        after = rng.poisson(0.04, S) + blk.after_hours_extra[t].astype(np.int64)
        # write the day
        out["opening_stock"][t] = opening
        out["received_units"][t] = rec_recorded
        out["sold_units"][t] = sold
        out["returned_units"][t] = returned
        out["transfer_in_units"][t] = tr_in
        out["transfer_out_units"][t] = tr_out
        out["adjustment_units"][t] = adj_recorded
        out["expected_closing"][t] = expected
        out["counted_closing"][t] = counted
        out["pos_scans"][t] = pos
        out["manual_entry_scans"][t] = manual
        out["void_count"][t] = void
        out["override_count"][t] = overr
        out["after_hours_scans"][t] = np.maximum(after, 0)
        out["receiving_scans"][t] = np.maximum(recv_scans, 0)
        out["on_promo"][t] = promo[t]
        # truth for planned (negative-coded) events where the effect actually happened
        planned_type = -blk.ev_type[t]
        happened = np.zeros(S, dtype=bool)
        happened |= (planned_type == TYPE_CODE["theft_external"]) & (loss > bg)
        happened |= (planned_type == TYPE_CODE["theft_internal"]) & ((loss > bg) | (blk.after_hours_extra[t] > 0))
        happened |= (planned_type == TYPE_CODE["scan_fraud"]) & ((loss > bg) | (refund > 0))
        happened |= (planned_type == TYPE_CODE["counting_error"]) & (ce | prev_count_err)
        happened |= (planned_type == TYPE_CODE["velocity_shift"]) & (np.abs(blk.lambda_mult[t] - 1) > 0.5)
        truth_type[t] = np.where(happened & (truth_type[t] == 0), planned_type, truth_type[t])
        truth_inc[t] = np.where(happened & (truth_inc[t] == 0), blk.ev_incident[t], truth_inc[t])
        theft_loss = np.where(planned_type > 0, np.maximum(loss - bg, 0), 0)
        truth_loss[t] = np.where(happened, np.maximum(truth_loss[t], theft_loss + refund + np.where(ce, np.maximum(phys_close - counted, 0), 0)), truth_loss[t])
        prev_count_err = ce
        # next morning: the count resets the book; physical stock carries on
        phys = phys_close
        book_open = counted

    def rows(a: np.ndarray, dtype: Any) -> np.ndarray:
        return np.ascontiguousarray(a.T).ravel().astype(dtype, copy=False)

    daily = {k: rows(out[k], DAILY_SPECS[k]) for k in out}
    daily["date_idx"] = np.tile(np.arange(T, dtype=np.int16), S)
    daily["store_code"] = np.repeat(st.astype(np.int16), T)
    daily["sku_code"] = np.repeat(sk.astype(np.int16), T)
    truth = {
        "truth_type": rows(truth_type, np.int8),
        "truth_incident": rows(truth_inc, np.int32),
        "truth_loss_units": rows(np.clip(truth_loss, 0, 32000), np.int16),
    }
    return daily, truth, blk.next_incident


# ---------------------------------------------------------------- loss-prevention flags (partial, noisy labels)
_LP_MAP = {
    "theft_external": "theft", "theft_internal": "theft", "scan_fraud": "theft", "counting_error": "counting_error",
    "receiving_error": "process_issue", "velocity_shift": "process_issue", "data_entry_error": "data_error",
}
_LP_SOURCE = {"theft": ["cctv_review", "stock_audit", "hotline"], "counting_error": ["stock_audit"], "process_issue": ["stock_audit", "till_audit"], "data_error": ["till_audit", "stock_audit"]}


def make_lp_flags(p: GenParams, daily: dict[str, np.ndarray], truth: dict[str, np.ndarray], stores: pd.DataFrame, skus: pd.DataFrame, dates: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    inc = truth["truth_incident"]
    hist = daily["date_idx"] < p.test_from_idx
    sel = (inc > 0) & hist
    idx = np.flatnonzero(sel)
    if len(idx):
        order = np.argsort(inc[idx], kind="stable")
        idx = idx[order]
        first = np.r_[True, inc[idx][1:] != inc[idx][:-1]]
        starts = idx[first]
    else:
        starts = idx
    rows = []
    unit_cost = skus["unit_cost"].to_numpy()
    for r in starts:
        typ = config.ANOMALY_TYPES[int(truth["truth_type"][r])]
        recall = (0.4 if typ in ("theft_external", "theft_internal", "scan_fraud") else 0.2) * p.lp_coverage / 0.4
        if rng.random() >= min(1.0, recall):
            continue
        ftype = _LP_MAP.get(typ, "process_issue")
        if rng.random() < 0.10:
            ftype = str(rng.choice([t for t in config.LP_FLAG_TYPES if t != ftype]))
        loss_units = int(truth["truth_loss_units"][inc == inc[r]].sum())
        rows.append((int(daily["date_idx"][r]), int(daily["store_code"][r]), int(daily["sku_code"][r]), ftype, str(rng.choice(_LP_SOURCE[ftype])), bool(rng.random() < 0.85), round(loss_units * float(unit_cost[daily["sku_code"][r]]), 2)))
    # false flags on ordinary rows with a visible variance (they look suspicious but are not)
    n_false = int(150 * p.n_rows / 1_000_000 * p.lp_coverage / 0.4)
    var = daily["expected_closing"].astype(np.int32) - daily["counted_closing"].astype(np.int32)
    cand = np.flatnonzero(hist & (inc == 0) & (var >= 2))
    if len(cand) and n_false:
        for r in rng.choice(cand, size=min(n_false, len(cand)), replace=False):
            ftype = str(rng.choice(config.LP_FLAG_TYPES, p=[0.5, 0.25, 0.15, 0.10]))
            rows.append((int(daily["date_idx"][r]), int(daily["store_code"][r]), int(daily["sku_code"][r]), ftype, str(rng.choice(_LP_SOURCE[ftype])), bool(rng.random() < 0.3), round(float(var[r]) * float(unit_cost[daily["sku_code"][r]]), 2)))
    df = pd.DataFrame(rows, columns=["date_idx", "store_code", "sku_code", "flag_type", "source", "confirmed", "loss_value_gbp"])
    df = df.sort_values(["date_idx", "store_code", "sku_code"]).reset_index(drop=True)
    df.insert(0, "flag_id", [f"LP{i + 1:05d}" for i in range(len(df))])
    df.insert(1, "date", dates[df["date_idx"].to_numpy()] if len(df) else [])
    df.insert(2, "store_id", stores["store_id"].to_numpy()[df["store_code"].to_numpy()] if len(df) else [])
    df.insert(3, "sku_id", skus["sku_id"].to_numpy()[df["sku_code"].to_numpy()] if len(df) else [])
    return df


# ---------------------------------------------------------------- whole dataset to disk
def generate_to_disk(ds_dir: Path, p: GenParams, on_progress: Callable[[float, str], None] | None = None, check_cancelled: Callable[[], None] | None = None) -> dict[str, Any]:
    rng = np.random.default_rng([p.seed, 0])
    stores = make_stores(p, rng)
    skus = make_skus(p, rng)
    dates = pd.date_range(config.SYN_START, periods=p.n_days, freq="D").strftime("%Y-%m-%d").to_numpy()
    n = p.n_rows
    daily_mm = colstore.preallocate(ds_dir / "daily", {k: (np.dtype(v), n) for k, v in DAILY_SPECS.items()})
    truth_mm = colstore.preallocate(ds_dir / "truth", {k: (np.dtype(v), n) for k, v in TRUTH_SPECS.items()})
    incident = 0
    block = config.GEN_BLOCK_STORES
    rows_per_store = p.n_skus * p.n_days
    for b, lo in enumerate(range(0, p.n_stores, block)):
        if check_cancelled:
            check_cancelled()
        hi = min(p.n_stores, lo + block)
        brng = np.random.default_rng([p.seed, b + 1])
        daily, truth, incident = simulate_block(p, stores, skus, lo, hi, brng, incident)
        a, z = lo * rows_per_store, hi * rows_per_store
        for k, v in daily.items():
            daily_mm[k][a:z] = v
        for k, v in truth.items():
            truth_mm[k][a:z] = v
        if on_progress:
            on_progress(hi / p.n_stores, f"Simulated {hi} of {p.n_stores} stores")
    colstore.flush(daily_mm)
    colstore.flush(truth_mm)
    daily_r = colstore.open_columns(ds_dir / "daily")
    truth_r = colstore.open_columns(ds_dir / "truth")
    lp = make_lp_flags(p, daily_r, truth_r, stores, skus, dates, np.random.default_rng([p.seed, 999]))
    return {"stores": stores.drop(columns=["_hotspot"]), "skus": skus.drop(columns=["_popularity", "_new_line"]), "dates": dates, "lp_flags": lp, "n_incidents": int(incident)}
