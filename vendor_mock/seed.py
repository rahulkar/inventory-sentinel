"""Seed the demo vendor's database once: simulate history plus future days, then reveal them one business day at a time."""
from __future__ import annotations

import threading
import time
import traceback
from datetime import date, timedelta
from typing import Callable

import numpy as np

from vendor_mock import db, settings
from vendor_mock.sim import synth
from vendor_mock.sim.constants import ANOMALY_TYPES, MEASURES

_thread: threading.Thread | None = None
_lock = threading.Lock()
INSERT_CHUNK = 200_000


def status() -> dict:
    return {
        "status": db.get_meta("status", "empty"),
        "progress": float(db.get_meta("seed_progress", "0") or 0),
        "message": db.get_meta("seed_message"),
    }


def _progress(f: float, msg: str) -> None:
    db.set_meta("seed_progress", round(f, 3))
    db.set_meta("seed_message", msg)


def seed(on_progress: Callable[[float, str], None] = _progress) -> None:
    c = db.conn()
    db.set_meta("status", "seeding")
    on_progress(0.0, "Simulating the estate")
    t0 = time.time()
    start = date.today() - timedelta(days=settings.HISTORY_DAYS)
    p = synth.GenParams(
        n_stores=settings.N_STORES, n_skus=settings.N_SKUS, n_days=settings.HISTORY_DAYS + settings.FUTURE_DAYS, seed=settings.SEED,
        anomaly_multiplier=settings.ANOMALY_MULTIPLIER, lp_coverage=settings.LP_COVERAGE, start_date=start.isoformat(),
    )
    for table in ("daily", "answer_key", "lp_flags", "stores", "skus", "tasks", "task_events"):
        c.execute(f"DELETE FROM {table}")
    c.commit()
    blocks_d: list[dict[str, np.ndarray]] = []
    blocks_t: list[dict[str, np.ndarray]] = []
    stores = skus = dates = None
    for kind, payload in synth.generate_blocks(p):
        if kind == "dims":
            stores, skus, dates = payload
            continue
        lo, hi, daily, truth = payload
        blocks_d.append(daily)
        blocks_t.append(truth)
        on_progress(0.4 * hi / p.n_stores, f"Simulated {hi} of {p.n_stores} stores")
    assert stores is not None and skus is not None and dates is not None
    daily = {k: np.concatenate([b[k] for b in blocks_d]) for k in blocks_d[0]}
    truth = {k: np.concatenate([b[k] for b in blocks_t]) for k in blocks_t[0]}
    del blocks_d, blocks_t
    lp = synth.make_lp_flags(p, daily, truth, stores, skus, dates, np.random.default_rng([p.seed, 999]))
    # ---- dimension tables
    c.executemany(
        "INSERT INTO stores VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(i, r.store_id, r.store_name, r.region, r.format, r.size_band, r.warehouse_team, float(r.footfall_index), r.opens_at, r.closes_at) for i, r in enumerate(stores.itertuples())],
    )
    c.executemany(
        "INSERT INTO skus VALUES (?,?,?,?,?,?,?,?)",
        [(i, r.sku_id, r.sku_name, r.category, float(r.unit_cost), float(r.unit_price), int(r.high_theft_risk), int(r.security_tagged)) for i, r in enumerate(skus.itertuples())],
    )
    c.commit()
    # ---- daily rows in primary-key order (day, store, sku) so the B-tree is appended, not shuffled
    order = np.lexsort((daily["sku_code"], daily["store_code"], daily["date_idx"]))
    cols = [daily["date_idx"], daily["store_code"], daily["sku_code"]] + [daily[m] for m in MEASURES]
    n = len(order)
    c.execute("PRAGMA synchronous=OFF")
    placeholders = ",".join("?" * (3 + len(MEASURES)))
    for a in range(0, n, INSERT_CHUNK):
        idx = order[a : a + INSERT_CHUNK]
        rows = np.column_stack([col[idx].astype(np.int64) for col in cols]).tolist()
        c.executemany(f"INSERT INTO daily VALUES ({placeholders})", rows)
        c.commit()
        on_progress(0.4 + 0.5 * min(n, a + INSERT_CHUNK) / n, f"Stored {min(n, a + INSERT_CHUNK):,} of {n:,} daily rows")
    hit = order[truth["truth_type"][order] > 0]
    tnames = np.array(ANOMALY_TYPES)
    c.executemany(
        "INSERT INTO answer_key VALUES (?,?,?,?,?,?)",
        zip(daily["date_idx"][hit].tolist(), daily["store_code"][hit].tolist(), daily["sku_code"][hit].tolist(), tnames[truth["truth_type"][hit]].tolist(), truth["truth_incident"][hit].tolist(), truth["truth_loss_units"][hit].tolist()),
    )
    c.executemany(
        "INSERT INTO lp_flags VALUES (?,?,?,?,?,?,?,?,?)",
        [(r.flag_id, int(r.date_idx), int(r.store_code), int(r.sku_code), r.flag_type, r.source, int(bool(r.confirmed)), float(r.loss_value_gbp), int(r.reported_idx)) for r in lp.itertuples()],
    )
    c.commit()
    c.execute("PRAGMA synchronous=NORMAL")
    for k, v in {
        "start_date": start.isoformat(), "n_days": p.n_days, "history_days": settings.HISTORY_DAYS, "n_stores": p.n_stores, "n_skus": p.n_skus,
        "seed": p.seed, "offset_days": 0, "seeded_at": date.today().isoformat(), "task_counter": 0, "seed_seconds": round(time.time() - t0, 1),
    }.items():
        db.set_meta(k, v)
    db.set_meta("status", "ready")
    on_progress(1.0, f"Ready: {n:,} daily rows in {time.time() - t0:.0f} s")


def _run() -> None:
    try:
        seed()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        db.set_meta("status", "failed")
        db.set_meta("seed_message", f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def start_background(force: bool = False) -> bool:
    """Seed in a background thread unless the database is ready (or already seeding). Returns True when started."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        if not force and db.get_meta("status") == "ready":
            return False
        db.set_meta("status", "seeding")
        _thread = threading.Thread(target=_run, name="vendor-seed", daemon=True)
        _thread.start()
        return True
