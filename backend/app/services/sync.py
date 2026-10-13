"""Sync a vendor connector into Sentinel: pull new days over MCP, keep a local copy, build a snapshot dataset.

Detectors learn "normal" from each vendor's own history, so every snapshot holds the last `window_days` of that
vendor's data and models are trained on it. Only the first sync pulls the whole window. Later syncs pull new days plus
`resync_days` of late corrections into the local copy, data/connectors/<id>/mirror/:
    state.json        watermark (last date pulled), store/SKU id lists (codes are positions), the fields pulled
    days/<date>.npz   one file per trading day: store/SKU codes plus the measures
    stores.csv / skus.csv / lp_flags.csv / answer_key.csv
Bulk pages never pass through the language model: chat only sees summaries.
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app import config
from app.mcp_compat import client_session, result_payload, run_sync as run_coro
from app.schemas import Connector, ConnectorSync, Job
from app.services import connectors, ingest, jobs, storage
from app.services.schema_spec import MEASURES

STEPS = [
    ("capabilities", "Checking the vendor"), ("dims", "Pulling stores and products"), ("daily", "Pulling daily stock movements"),
    ("flags", "Pulling loss-prevention flags"), ("tasks", "Reading vendor task outcomes"), ("build", "Building the snapshot"), ("retention", "Tidying old snapshots"),
]


class SyncError(connectors.ConnectorError):
    pass


def mirror_dir(connector_id: str) -> Path:
    return config.CONNECTORS_DIR / storage.check_id(connector_id) / "mirror"


def _state(connector_id: str) -> dict[str, Any]:
    p = mirror_dir(connector_id) / "state.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _save_state(connector_id: str, state: dict[str, Any]) -> None:
    storage.atomic_write_text(mirror_dir(connector_id) / "state.json", json.dumps(state, indent=1))


def _epoch(d: str) -> int:
    return int(np.datetime64(str(d)[:10], "D").astype(np.int64))


def _iso(day: int) -> str:
    return str(np.datetime64(int(day), "D"))


def _decode(col: Any) -> list[Any] | np.ndarray:
    if isinstance(col, dict) and "dict" in col:
        lut = np.asarray(col["dict"], dtype=object)
        return lut[np.asarray(col["idx"], dtype=np.int64)] if len(col["idx"]) else np.asarray([], dtype=object)
    return col


def _codes(ids: np.ndarray, known: list[str], index: dict[str, int]) -> np.ndarray:
    uniq, inv = np.unique(np.asarray(ids, dtype=str), return_inverse=True)
    lut = np.empty(len(uniq), dtype=np.int32)
    for i, s in enumerate(uniq):
        code = index.get(s)
        if code is None:
            code = index[s] = len(known)
            known.append(s)
        lut[i] = code
    return lut[inv]


# ---------------------------------------------------------------- pulling (one MCP session for the whole sync)
async def _pull(c: Connector, plan: dict[str, Any], ctx: Any) -> dict[str, Any]:
    async with client_session(c.url, connectors.headers(c), config.MCP_CALL_TIMEOUT_S) as s:

        async def call(name: str, **args: Any) -> Any:
            return result_payload(await s.call_tool(name, {k: v for k, v in args.items() if v is not None}))

        async def pages(name: str, **args: Any) -> list[Any]:
            out, cursor = [], None
            while True:
                ctx.check_cancelled()
                pg = await call(name, cursor=cursor, **args)
                out.append(pg)
                cursor = pg.get("next_cursor")
                if not cursor:
                    return out

        ctx.step("dims", "Pulling stores and products")
        stores = [it for pg in await pages("list_stores", page_size=5000) for it in pg["items"]]
        skus = [it for pg in await pages("list_skus", page_size=5000) for it in pg["items"]]
        ctx.progress(8)
        ctx.step("daily", f"Pulling daily stock movements from {plan['since']}")
        daily_pages: list[dict[str, Any]] = []
        cursor = None
        span = max(1, _epoch(plan["until"]) - _epoch(plan["since"]) + 1)
        rows = 0
        while True:
            ctx.check_cancelled()
            pg = await call("get_daily_movements", since=plan["since"], until=plan["until"], fields=plan["fields"], cursor=cursor, page_size=config.SYNC_PAGE_SIZE)
            daily_pages.append(pg)
            rows += int(pg.get("row_count") or 0)
            if pg.get("row_count"):
                last = _decode(pg["data"]["date"])[-1]
                ctx.progress(8 + 62 * min(1.0, (_epoch(last) - _epoch(plan["since"]) + 1) / span), f"{rows:,} rows, through {last}")
            cursor = pg.get("next_cursor")
            if not cursor:
                break
        ctx.step("flags", "Pulling loss-prevention flags")
        flags = [it for pg in await pages("get_lp_flags", since=plan["window_start"], until=plan["until"], page_size=20000) for it in pg["items"]] if plan["lp_flags"] else []
        ak_pages = await pages("get_answer_key", since=plan["since"], until=plan["until"], page_size=config.SYNC_PAGE_SIZE) if plan["answer_key"] else []
        ctx.progress(74)
        return {"stores": stores, "skus": skus, "daily": daily_pages, "flags": flags, "answer_key": ak_pages, "rows": rows}


# ---------------------------------------------------------------- the job
def start_job(connector_id: str | None, full: bool = False, title: str | None = None) -> Job:
    c = connectors.get(connector_id)
    if not c.enabled:
        raise ValueError(f"{c.name} is switched off; enable it first.")
    busy = [j for j in jobs.list_jobs(active_only=True) if j.params.get("connector_id") == c.id]
    if busy:
        raise ValueError(f"{c.name} is already syncing ({busy[0].title}).")
    last = c.last_sync
    est = (last.seconds if last and last.seconds else None) or (config.TIMING["sync_s_per_1m"] * 1.2 + 10)
    return jobs.submit(
        "sync", title or f"Sync {c.name}", lambda ctx: run_sync(ctx, c.id, full),
        params={"connector_id": c.id, "full": full}, steps=STEPS, estimate_seconds=round(est, 1),
    )


def run_sync(ctx: Any, connector_id: str, full: bool = False) -> dict[str, Any]:
    """The sync body; also called inline by the scheduled pipeline (ctx may be a jobs.ScopedContext)."""
    t0 = time.time()
    c = connectors.get(connector_id)
    prev = c.last_sync
    connectors.record_sync(c.id, ConnectorSync(at=storage.now_iso(), status="running", job_id=ctx.job_id, synced_through=prev.synced_through if prev else None, dataset_id=prev.dataset_id if prev else None))
    try:
        out = _sync(ctx, c, full, prev)
    except BaseException as exc:
        err = "Cancelled." if isinstance(exc, jobs.JobCancelled) else str(exc) or type(exc).__name__
        connectors.record_sync(c.id, ConnectorSync(at=storage.now_iso(), status="failed", job_id=ctx.job_id, error=err, synced_through=prev.synced_through if prev else None, dataset_id=prev.dataset_id if prev else None, seconds=round(time.time() - t0, 1)))
        raise
    connectors.record_sync(c.id, ConnectorSync(
        at=storage.now_iso(), status="ok", job_id=ctx.job_id, dataset_id=out["dataset_id"], rows=out["rows"], days_pulled=out["days_pulled"],
        synced_through=out["synced_through"], warnings=out["warnings"], seconds=round(time.time() - t0, 1),
    ))
    return out


def _sync(ctx: Any, c: Connector, full: bool, prev: ConnectorSync | None) -> dict[str, Any]:
    warnings: list[str] = []
    ctx.step("capabilities", "Checking the vendor")
    caps = connectors.call(c, "get_capabilities")
    if not isinstance(caps, dict) or caps.get("contract") != connectors.CONTRACT:
        raise SyncError(f"{c.name} does not implement the {connectors.CONTRACT} contract.", "contract")
    if caps.get("status") != "ready":
        raise SyncError(f"{c.name} is not ready yet ({caps.get('status')}): {((caps.get('seeding') or {}).get('message') or '')}".strip(), "not_ready")
    connectors.patch(c.id, capabilities=caps, tested_at=storage.now_iso())
    rng = caps.get("data_range") or {}
    if not rng.get("last_date"):
        raise SyncError(f"{c.name} has no closed trading days yet.", "no_data")
    vendor_fields = (caps.get("fields") or {}).get("daily") or list(MEASURES)
    fields = [f for f in MEASURES if f in vendor_fields]
    if "counted_closing" not in fields or not ("expected_closing" in fields or {"opening_stock", "sold_units"} <= set(fields)):
        raise SyncError(f"{c.name} does not supply counted and expected (or opening + sold) stock, which detection needs.", "contract")
    until = rng["last_date"]
    window_start = max(_epoch(rng.get("first_date") or until), _epoch(until) - c.window_days + 1)
    state = {} if full else _state(c.id)
    if state.get("fields") != fields or state.get("window_days") != c.window_days:
        state = {}  # schema or window changed: rebuild the local copy
    since = window_start
    if state.get("watermark"):
        since = max(window_start, min(_epoch(state["watermark"]) + 1, _epoch(until)) - c.resync_days)
    if state.get("watermark") and _epoch(state["watermark"]) > _epoch(until):
        warnings.append(f"The vendor's data now ends on {until}, before the last sync ({state['watermark']}); the local copy was rebuilt.")
        state, since = {}, window_start
    feats = caps.get("features") or {}
    plan = {
        "since": _iso(since), "until": until, "window_start": _iso(window_start), "fields": fields,
        "lp_flags": bool(feats.get("lp_flags", True)), "answer_key": bool(feats.get("answer_key")) and c.use_answer_key,
    }
    ctx.progress(4)
    try:
        pulled = run_coro(lambda: _pull(c, plan, ctx))
    except BaseException as exc:  # noqa: BLE001
        leaf = connectors.leaf(exc)
        if isinstance(leaf, jobs.JobCancelled):
            raise leaf from None
        raise connectors._friendly(exc, c) from exc
    # ---- update the local copy
    md = mirror_dir(c.id)
    if not state:  # fresh copy: codes in old day files refer to the old id lists
        storage.safe_rmtree(md / "days")
    (md / "days").mkdir(parents=True, exist_ok=True)
    store_ids: list[str] = list(state.get("store_ids") or [])
    sku_ids: list[str] = list(state.get("sku_ids") or [])
    st_index = {s: i for i, s in enumerate(store_ids)}
    sk_index = {s: i for i, s in enumerate(sku_ids)}
    for it in pulled["stores"]:
        _codes(np.asarray([str(it["store_id"])]), store_ids, st_index)
    for it in pulled["skus"]:
        _codes(np.asarray([str(it["sku_id"])]), sku_ids, sk_index)
    pd.DataFrame(pulled["stores"]).astype({"store_id": str}).to_csv(md / "stores.csv", index=False)
    pd.DataFrame(pulled["skus"]).astype({"sku_id": str}).to_csv(md / "skus.csv", index=False)
    parts: dict[str, list[np.ndarray]] = {k: [] for k in ["day", "store", "sku", *fields]}
    for pg in pulled["daily"]:
        if not pg.get("row_count"):
            continue
        d = pg["data"]
        dates = np.asarray(_decode(d["date"]), dtype=str)
        parts["day"].append(dates.astype("datetime64[D]").astype(np.int64))
        parts["store"].append(_codes(np.asarray(_decode(d["store_id"])), store_ids, st_index))
        parts["sku"].append(_codes(np.asarray(_decode(d["sku_id"])), sku_ids, sk_index))
        for f in fields:
            parts[f].append(np.asarray(d[f], dtype=np.int64))
    days_pulled = 0
    if parts["day"]:
        day = np.concatenate(parts["day"])
        cols = {k: np.concatenate(v) for k, v in parts.items() if k != "day"}
        order = np.argsort(day, kind="stable")
        day = day[order]
        cols = {k: v[order] for k, v in cols.items()}
        bounds = np.flatnonzero(np.r_[True, day[1:] != day[:-1], True])
        for a, b in zip(bounds[:-1], bounds[1:]):
            np.savez(md / "days" / f"{_iso(int(day[a]))}.npz", **{k: v[a:b].astype(np.int32) for k, v in cols.items()})
            days_pulled += 1
        del day, cols
    pd.DataFrame(pulled["flags"]).to_csv(md / "lp_flags.csv", index=False)
    if plan["answer_key"]:
        frames = []
        for pg in pulled["answer_key"]:
            if pg.get("row_count"):
                frames.append(pd.DataFrame({k: _decode(v) for k, v in pg["data"].items()}))
        new_ak = pd.concat(frames) if frames else pd.DataFrame(columns=["date", "store_id", "sku_id", "truth_type", "truth_incident", "truth_loss_units"])
        old_ak = pd.read_csv(md / "answer_key.csv", dtype={"store_id": str, "sku_id": str, "date": str}) if (md / "answer_key.csv").exists() and state else new_ak.iloc[0:0]
        old_ak = old_ak[(old_ak["date"] >= plan["window_start"]) & (old_ak["date"] < plan["since"])]
        pd.concat([old_ak, new_ak]).to_csv(md / "answer_key.csv", index=False)
    elif (md / "answer_key.csv").exists():
        (md / "answer_key.csv").unlink()
    for f in (md / "days").glob("*.npz"):
        if f.stem < plan["window_start"] or f.stem > until:
            f.unlink()
    state = {**state, "watermark": until, "store_ids": store_ids, "sku_ids": sku_ids, "fields": fields, "window_days": c.window_days, "updated_at": storage.now_iso()}
    _save_state(c.id, state)
    # ---- vendor task outcomes (non-fatal)
    ctx.step("tasks", "Reading vendor task outcomes")
    if feats.get("tasks"):
        try:
            from app.services import vendor_tasks

            changed = vendor_tasks.refresh(c)
            if changed:
                ctx.progress(76, f"{changed} task update(s) from {c.name}")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not read vendor task updates: {exc}")
    # ---- data-quality checks
    have = sorted(f.stem for f in (md / "days").glob("*.npz"))
    expected_days = (_epoch(until) - window_start) + 1
    if len(have) < expected_days:
        missing = sorted(set(_iso(d) for d in range(window_start, _epoch(until) + 1)) - set(have))
        warnings.append(f"{len(missing)} day(s) missing from the vendor feed (e.g. {', '.join(missing[:3])}); they are treated as gaps.")
    if prev and prev.status == "ok" and prev.synced_through == until:
        warnings.append(f"No new trading days since the last sync (data still ends {until}). The vendor feed may be stale; see SOP data-feed-failure.")
    sizes = [(md / "days" / f"{d}.npz").stat().st_size for d in have[-15:]]
    if len(sizes) >= 8 and sizes[-1] < 0.8 * float(np.median(sizes[:-1])):
        warnings.append(f"The latest day ({have[-1]}) has noticeably fewer rows than usual; the vendor may still be loading it.")
    # ---- build the snapshot
    ctx.step("build", "Building the snapshot")
    ds_id = storage.new_id("ds")
    ctx.progress(78)
    try:
        meta = _build_snapshot(ctx, c, ds_id, have, store_ids, sku_ids, fields, plan, caps, warnings)
    except BaseException:
        storage._dataset_cache.pop(ds_id)
        gc.collect()
        storage.safe_rmtree(storage.dataset_dir(ds_id))
        raise
    ctx.step("retention", "Tidying old snapshots")
    removed = apply_retention(c, keep_ids={meta.id}, current_job=ctx.job_id)
    if removed:
        ctx.progress(99, f"Removed {len(removed)} old snapshot(s)")
    return {
        "connector_id": c.id, "dataset_id": meta.id, "rows": meta.n_rows, "days_pulled": days_pulled, "synced_through": until,
        "window_start": plan["window_start"], "warnings": warnings, "removed_snapshots": removed, "vendor_rows_pulled": pulled["rows"],
    }


def _build_snapshot(ctx: Any, c: Connector, ds_id: str, have: list[str], store_ids: list[str], sku_ids: list[str], fields: list[str], plan: dict[str, Any], caps: dict[str, Any], warnings: list[str]):
    md = mirror_dir(c.id)
    parts: dict[str, list[np.ndarray]] = {k: [] for k in ["day", "store", "sku", *fields]}
    for d in have:
        with np.load(md / "days" / f"{d}.npz") as z:
            n = len(z["store"])
            parts["day"].append(np.full(n, _epoch(d), dtype=np.int64))
            parts["store"].append(z["store"].astype(np.int64))
            parts["sku"].append(z["sku"].astype(np.int64))
            for f in fields:
                parts[f].append(z[f].astype(np.int64))
    if not parts["day"]:
        raise SyncError(f"{c.name} returned no daily rows for {plan['window_start']} to {plan['until']}.", "no_data")
    arrays = {k: np.concatenate(v) for k, v in parts.items()}
    del parts
    read = lambda name, dt: pd.read_csv(md / name, dtype=dt) if (md / name).exists() and (md / name).stat().st_size > 2 else None  # noqa: E731
    lp = read("lp_flags.csv", {"store_id": str, "sku_id": str})
    if lp is not None and "flag_id" in lp:
        lp = lp.drop(columns=[c_ for c_ in ("reported_on",) if c_ in lp])
    ak = read("answer_key.csv", {"store_id": str, "sku_id": str}) if plan["answer_key"] else None
    vendor = caps.get("vendor") or {}
    meta = ingest.build_dataset(
        ds_id, store_ids=store_ids, sku_ids=sku_ids, store=arrays.pop("store"), sku=arrays.pop("sku"), day=arrays.pop("day"), meas=arrays,
        stores_in=read("stores.csv", {"store_id": str}), skus_in=read("skus.csv", {"sku_id": str}), lp_in=lp, answer_key_in=ak, sku_meta={},
        name=f"{c.name} · {plan['window_start']} to {plan['until']}", kind="connector",
        params={
            "connector_id": c.id, "connector_name": c.name, "synced_through": plan["until"], "window_start": plan["window_start"], "window_days": c.window_days,
            "vendor": vendor.get("name"), "vendor_system": vendor.get("system"), "answer_key_demo_only": bool(plan["answer_key"]), "synced_at": storage.now_iso(),
        },
        detection=None, warnings=list(warnings), on_progress=lambda f, m: ctx.progress(78 + 20 * f, m),
    )
    return meta


# ---------------------------------------------------------------- retention
def protected_datasets(current_job: str | None = None) -> set[str]:
    """Snapshots that must survive retention: the model in use, schedules' fixed models, anything a running job uses."""
    keep: set[str] = set()
    active = storage.get_active_model_id()
    for mid in [active] + _schedule_model_ids():
        m = storage.get_model_summary(mid) if mid else None
        if m is not None:
            keep.add(m.dataset_id)
            if getattr(m, "parent_model_id", None):
                parent = storage.get_model_summary(m.parent_model_id)
                if parent is not None:
                    keep.add(parent.dataset_id)
    for j in jobs.list_jobs(active_only=True):
        if j.job_id != current_job and j.params.get("dataset_id"):
            keep.add(j.params["dataset_id"])
    return keep


def _schedule_model_ids() -> list[str]:
    try:
        from app.services import scheduler

        return [s.pipeline.model_id for s in scheduler.list_all() if s.pipeline.model_policy == "fixed" and s.pipeline.model_id]
    except Exception:  # noqa: BLE001
        return []


def apply_retention(c: Connector, keep_ids: set[str] | None = None, current_job: str | None = None) -> list[str]:
    snaps = sorted(connectors.connector_datasets(c.id), key=lambda d: d.created_at, reverse=True)
    keep = set(keep_ids or set()) | {d.id for d in snaps[: c.retention]} | protected_datasets(current_job)
    removed = []
    for d in snaps[c.retention :]:
        if d.id in keep:
            continue
        if storage.delete_dataset(d.id):
            removed.append(d.id)
    return removed


def latest_dataset_id(connector_id: str) -> str | None:
    snaps = sorted(connectors.connector_datasets(connector_id), key=lambda d: d.created_at, reverse=True)
    return snaps[0].id if snaps else None

