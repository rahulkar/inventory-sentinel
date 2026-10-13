"""The demo vendor's data access: the business clock, the connector contract and the task inbox.

Everything here is plain sync code over SQLite; `connector.py` exposes it over MCP and `ui.py` renders it as pages.
Rows after the business clock's "yesterday" exist in the database (they were simulated up front) but are never
returned, so advancing the clock is how new trading days arrive.
"""
from __future__ import annotations

import base64
import json
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np

from vendor_mock import db, settings
from vendor_mock.sim.constants import MEASURES


class VendorError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- business clock
def _ready() -> None:
    st = db.get_meta("status")
    if st != "ready":
        raise VendorError("not_ready", "The vendor system is still loading its data; try again in a minute." if st == "seeding" else "The vendor system has no data yet.")


def start_date() -> date:
    return date.fromisoformat(db.get_meta("start_date") or date.today().isoformat())


def n_days() -> int:
    return int(db.get_meta("n_days", "0") or 0)


def visible_through() -> int:
    """Index of the last trading day the vendor has closed (business date minus one); follows the calendar plus any fast-forward."""
    offset = int(db.get_meta("offset_days", "0") or 0)
    return max(-1, min(n_days() - 1, (date.today() - start_date()).days - 1 + offset))


def business_date() -> date:
    return start_date() + timedelta(days=visible_through() + 1)


def day_str(i: int) -> str:
    return (start_date() + timedelta(days=int(i))).isoformat()


def _day(s: str | None, default: int) -> int:
    if not s:
        return default
    try:
        return (date.fromisoformat(str(s)[:10]) - start_date()).days
    except ValueError as exc:
        raise VendorError("bad_request", f"Dates are ISO YYYY-MM-DD; got {s!r}.") from exc


def advance(days: int) -> dict[str, Any]:
    _ready()
    room = n_days() - 1 - visible_through()
    step = max(0, min(int(days), room))
    db.set_meta("offset_days", int(db.get_meta("offset_days", "0") or 0) + step)
    return {"advanced": step, "business_date": business_date().isoformat(), "days_left": room - step}


def clock() -> dict[str, Any]:
    vis = visible_through()
    return {
        "business_date": business_date().isoformat(), "data_through": day_str(vis) if vis >= 0 else None, "first_date": day_str(0),
        "days_left": n_days() - 1 - vis, "offset_days": int(db.get_meta("offset_days", "0") or 0),
    }


# ---------------------------------------------------------------- cursors
def _enc(obj: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode().rstrip("=")


def _dec(cursor: str) -> dict[str, Any]:
    try:
        pad = "=" * (-len(cursor) % 4)
        return json.loads(base64.urlsafe_b64decode(cursor + pad))
    except Exception as exc:  # noqa: BLE001
        raise VendorError("bad_cursor", "The cursor is not valid; start again without one.") from exc


def _page_size(n: int | None) -> int:
    return max(1, min(int(n or settings.DEFAULT_PAGE_SIZE), settings.MAX_PAGE_SIZE))


def _dict_col(values: np.ndarray, labels: dict[int, str] | None = None, fmt=None) -> dict[str, Any]:
    uniq, inv = np.unique(values, return_inverse=True)
    names = [fmt(int(u)) if fmt else (labels or {}).get(int(u), str(u)) for u in uniq]
    return {"dict": names, "idx": inv.astype(np.int64).tolist()}


def _ids(table: str) -> dict[int, str]:
    col = "store" if table == "stores" else "sku"
    return {r[0]: r[1] for r in db.conn().execute(f"SELECT {col}_code, {col}_id FROM {table}")}


def _codes(table: str) -> dict[str, int]:
    return {v: k for k, v in _ids(table).items()}


# ---------------------------------------------------------------- the connector contract
def capabilities() -> dict[str, Any]:
    st = db.get_meta("status", "empty")
    out: dict[str, Any] = {
        "contract": settings.CONTRACT, "version": settings.CONTRACT_VERSION,
        "vendor": {"name": settings.VENDOR_NAME, "system": settings.SYSTEM_NAME}, "status": "ready" if st == "ready" else st,
        "timezone": settings.TIMEZONE, "currency": settings.CURRENCY,
        "paging": {"default_page_size": settings.DEFAULT_PAGE_SIZE, "max_page_size": settings.MAX_PAGE_SIZE}, "encodings": ["columnar-json"],
        "fields": {"daily": list(MEASURES)},
        "features": {"lp_flags": True, "tasks": True, "live_lookup": True, "answer_key": True, "answer_key_demo_only": True},
        "task_types": settings.TASK_TYPES, "task_priorities": settings.TASK_PRIORITIES, "task_statuses": settings.TASK_STATUSES, "task_outcomes": settings.TASK_OUTCOMES,
        "backoffice_url": settings.PUBLIC_URL,
    }
    if st == "ready":
        c = db.conn()
        vis = visible_through()
        out["data_range"] = {"first_date": day_str(0), "last_date": day_str(vis) if vis >= 0 else None}
        out["business_date"] = business_date().isoformat()
        out["counts"] = {"stores": c.execute("SELECT COUNT(*) FROM stores").fetchone()[0], "skus": c.execute("SELECT COUNT(*) FROM skus").fetchone()[0]}
    else:
        out["seeding"] = {"progress": float(db.get_meta("seed_progress", "0") or 0), "message": db.get_meta("seed_message")}
    return out


def _list_dim(table: str, cursor: str | None, page_size: int | None) -> dict[str, Any]:
    _ready()
    col = "store_code" if table == "stores" else "sku_code"
    after = int(_dec(cursor)["k"]) if cursor else -1
    n = _page_size(page_size)
    rows = [dict(r) for r in db.conn().execute(f"SELECT * FROM {table} WHERE {col} > ? ORDER BY {col} LIMIT ?", (after, n))]
    nxt = _enc({"k": rows[-1][col]}) if len(rows) == n else None
    for r in rows:
        r.pop(col, None)
    return {"items": rows, "next_cursor": nxt}


def list_stores(cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    return _list_dim("stores", cursor, page_size)


def list_skus(cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    return _list_dim("skus", cursor, page_size)


def daily_movements(since: str, until: str | None = None, fields: list[str] | None = None, cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    _ready()
    vis = visible_through()
    fields = list(fields or MEASURES)
    bad = [f for f in fields if f not in MEASURES]
    if bad:
        raise VendorError("bad_request", f"Unknown field(s): {', '.join(bad)}.")
    if cursor:
        cur = _dec(cursor)
        lo, hi, key = int(cur["s"]), int(cur["u"]), cur["k"]
    else:
        lo, hi, key = max(0, _day(since, 0)), min(vis, _day(until, vis)), None
    n = _page_size(page_size)
    sql = f"SELECT day, store_code, sku_code, {', '.join(fields)} FROM daily WHERE day >= ? AND day <= ?"
    args: list[Any] = [lo, hi]
    if key:
        sql += " AND (day, store_code, sku_code) > (?, ?, ?)"
        args += list(key)
    sql += " ORDER BY day, store_code, sku_code LIMIT ?"
    args.append(n)
    cur_ = db.conn().cursor()
    cur_.row_factory = None
    rows = cur_.execute(sql, args).fetchall()
    arr = np.array(rows, dtype=np.int64).reshape(len(rows), 3 + len(fields))
    data: dict[str, Any] = {}
    if len(rows):
        data["date"] = _dict_col(arr[:, 0], fmt=day_str)
        data["store_id"] = _dict_col(arr[:, 1], _ids("stores"))
        data["sku_id"] = _dict_col(arr[:, 2], _ids("skus"))
        for j, f in enumerate(fields):
            data[f] = arr[:, 3 + j].tolist()
    nxt = _enc({"s": lo, "u": hi, "k": [int(x) for x in arr[-1, :3]]}) if len(rows) == n else None
    return {
        "since": day_str(lo), "until": day_str(hi) if hi >= 0 else None, "as_of": business_date().isoformat(), "columns": ["date", "store_id", "sku_id", *fields],
        "row_count": len(rows), "next_cursor": nxt, "encoding": "columnar-json", "data": data,
    }


def lp_flags(since: str | None = None, until: str | None = None, cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    """Loss-prevention flags reported so far (a flag shows up 2-10 days after the day it concerns)."""
    _ready()
    vis = visible_through()
    after = _dec(cursor)["k"] if cursor else ""
    n = _page_size(page_size)
    rows = db.conn().execute(
        "SELECT f.*, s.store_id, k.sku_id FROM lp_flags f JOIN stores s USING(store_code) JOIN skus k USING(sku_code) "
        "WHERE f.reported_day <= ? AND f.day >= ? AND f.day <= ? AND f.flag_id > ? ORDER BY f.flag_id LIMIT ?",
        (vis, max(0, _day(since, 0)), min(vis, _day(until, vis)), after, n),
    ).fetchall()
    items = [
        {"flag_id": r["flag_id"], "date": day_str(r["day"]), "store_id": r["store_id"], "sku_id": r["sku_id"], "flag_type": r["flag_type"], "source": r["source"],
         "confirmed": bool(r["confirmed"]), "loss_value_gbp": r["loss_value_gbp"], "reported_on": day_str(r["reported_day"])}
        for r in rows
    ]
    return {"items": items, "next_cursor": _enc({"k": items[-1]["flag_id"]}) if len(items) == n else None}


def answer_key(since: str | None = None, until: str | None = None, cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    """Demo only: the injected anomalies, so Sentinel can score itself. A real vendor never has this."""
    _ready()
    vis = visible_through()
    if cursor:
        cur = _dec(cursor)
        lo, hi, key = int(cur["s"]), int(cur["u"]), cur["k"]
    else:
        lo, hi, key = max(0, _day(since, 0)), min(vis, _day(until, vis)), None
    n = _page_size(page_size)
    sql = "SELECT day, store_code, sku_code, truth_type, truth_incident, truth_loss_units FROM answer_key WHERE day >= ? AND day <= ?"
    args: list[Any] = [lo, hi]
    if key:
        sql += " AND (day, store_code, sku_code) > (?, ?, ?)"
        args += list(key)
    sql += " ORDER BY day, store_code, sku_code LIMIT ?"
    args.append(n)
    rows = db.conn().execute(sql, args).fetchall()
    data: dict[str, Any] = {}
    if rows:
        arr = np.array([(r[0], r[1], r[2]) for r in rows], dtype=np.int64)
        data["date"] = _dict_col(arr[:, 0], fmt=day_str)
        data["store_id"] = _dict_col(arr[:, 1], _ids("stores"))
        data["sku_id"] = _dict_col(arr[:, 2], _ids("skus"))
        data["truth_type"] = [r[3] for r in rows]
        data["truth_incident"] = [r[4] for r in rows]
        data["truth_loss_units"] = [r[5] for r in rows]
    nxt = _enc({"s": lo, "u": hi, "k": [rows[-1][0], rows[-1][1], rows[-1][2]]}) if len(rows) == n else None
    return {"since": day_str(lo), "until": day_str(hi) if hi >= 0 else None, "columns": ["date", "store_id", "sku_id", "truth_type", "truth_incident", "truth_loss_units"], "row_count": len(rows), "next_cursor": nxt, "encoding": "columnar-json", "data": data, "demo_only": True}


def stock_position(store_id: str, sku_id: str, days: int = 7) -> dict[str, Any]:
    _ready()
    c = db.conn()
    st = c.execute("SELECT * FROM stores WHERE store_id = ?", (store_id,)).fetchone()
    sk = c.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,)).fetchone()
    if st is None or sk is None:
        raise VendorError("not_found", f"Unknown {'store ' + store_id if st is None else 'SKU ' + sku_id}.")
    vis = visible_through()
    days = max(1, min(int(days or 7), 14))
    rows = c.execute(
        "SELECT * FROM daily WHERE store_code = ? AND sku_code = ? AND day <= ? AND day > ? ORDER BY day DESC",
        (st["store_code"], sk["sku_code"], vis, vis - days),
    ).fetchall()
    last = [
        {"date": day_str(r["day"]), "opening": r["opening_stock"], "received": r["received_units"], "sold": r["sold_units"], "returned": r["returned_units"],
         "adjusted": r["adjustment_units"], "expected_closing": r["expected_closing"], "counted_closing": r["counted_closing"], "variance": r["expected_closing"] - r["counted_closing"]}
        for r in rows
    ]
    return {
        "store": {"store_id": st["store_id"], "store_name": st["store_name"], "region": st["region"]},
        "sku": {"sku_id": sk["sku_id"], "sku_name": sk["sku_name"], "category": sk["category"], "unit_cost": sk["unit_cost"]},
        "as_of": business_date().isoformat(), "on_hand": last[0]["counted_closing"] if last else None, "last_days": last,
    }


# ---------------------------------------------------------------- tasks (write-back from Sentinel)
def _task_out(r: Any, with_events: bool = False) -> dict[str, Any]:
    d = dict(r)
    d["evidence"] = json.loads(d.pop("evidence_json") or "null")
    if with_events:
        d["events"] = [dict(e) for e in db.conn().execute("SELECT at, actor, event, note FROM task_events WHERE task_id = ? ORDER BY id", (d["task_id"],))]
    return d


def _event(task_id: str, actor: str, event: str, note: str | None = None) -> None:
    db.conn().execute("INSERT INTO task_events(task_id, at, actor, event, note) VALUES (?,?,?,?,?)", (task_id, _now(), actor, event, note))


def create_task(
    type: str, store_id: str, title: str, description: str = "", priority: str = "normal", idempotency_key: str | None = None,
    sku_id: str | None = None, external_ref: str | None = None, source_alert_id: str | None = None, sop_id: str | None = None,
    evidence: dict[str, Any] | None = None, due_by: str | None = None,
) -> dict[str, Any]:
    _ready()
    if type not in settings.TASK_TYPES:
        raise VendorError("bad_request", f"Task type must be one of {', '.join(settings.TASK_TYPES)}.")
    if priority not in settings.TASK_PRIORITIES:
        raise VendorError("bad_request", f"Priority must be one of {', '.join(settings.TASK_PRIORITIES)}.")
    if not (title or "").strip():
        raise VendorError("bad_request", "A task needs a title.")
    c = db.conn()
    if store_id not in _codes("stores"):
        raise VendorError("not_found", f"Unknown store {store_id}.")
    if sku_id and sku_id not in _codes("skus"):
        raise VendorError("not_found", f"Unknown SKU {sku_id}.")
    with c:
        if idempotency_key:
            row = c.execute("SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if row is not None:
                return {"task_id": row["task_id"], "status": row["status"], "created": False, "created_at": row["created_at"]}
        n = int(db.get_meta("task_counter", "0") or 0) + 1
        c.execute("INSERT INTO meta(key, value) VALUES('task_counter', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(n),))
        task_id = f"VT-{n:06d}"
        now = _now()
        c.execute(
            "INSERT INTO tasks(task_id, idempotency_key, type, status, priority, title, description, store_id, sku_id, external_ref, source_alert_id, sop_id, evidence_json, due_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, idempotency_key, type, "open", priority, title.strip()[:200], (description or "")[:4000], store_id, sku_id, external_ref, source_alert_id, sop_id, json.dumps(evidence) if evidence else None, due_by, now, now),
        )
        _event(task_id, "sentinel", "created", f"{type} · {priority}")
    return {"task_id": task_id, "status": "open", "created": True, "created_at": now}


def list_tasks(status: str | None = None, store_id: str | None = None, external_ref: str | None = None, updated_since: str | None = None, cursor: str | None = None, page_size: int | None = 100) -> dict[str, Any]:
    _ready()
    sql = "SELECT * FROM tasks WHERE 1=1"
    args: list[Any] = []
    for col, val in (("status", status), ("store_id", store_id), ("external_ref", external_ref)):
        if val:
            sql += f" AND {col} = ?"
            args.append(val)
    if updated_since:
        sql += " AND updated_at >= ?"
        args.append(updated_since)
    if cursor:
        k = _dec(cursor)["k"]
        sql += " AND (updated_at, task_id) > (?, ?)"
        args += [k[0], k[1]]
    n = max(1, min(int(page_size or 100), 500))
    sql += " ORDER BY updated_at, task_id LIMIT ?"
    args.append(n)
    items = [_task_out(r) for r in db.conn().execute(sql, args)]
    return {"items": items, "next_cursor": _enc({"k": [items[-1]["updated_at"], items[-1]["task_id"]]}) if len(items) == n else None}


def get_task(task_id: str) -> dict[str, Any]:
    _ready()
    r = db.conn().execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if r is None:
        raise VendorError("not_found", f"Unknown task {task_id}.")
    return _task_out(r, with_events=True)


def update_task(task_id: str, status: str | None = None, outcome: str | None = None, outcome_units: int | None = None, note: str | None = None, assignee: str | None = None, actor: str = "back-office user") -> dict[str, Any]:
    """Store-side work on a task (the back-office UI); Sentinel reads the result with list_tasks / get_task."""
    t = get_task(task_id)
    if status and status not in settings.TASK_STATUSES:
        raise VendorError("bad_request", f"Status must be one of {', '.join(settings.TASK_STATUSES)}.")
    if outcome and outcome not in settings.TASK_OUTCOMES:
        raise VendorError("bad_request", f"Outcome must be one of {', '.join(settings.TASK_OUTCOMES)}.")
    if status == "done" and not (outcome or t["outcome"]):
        raise VendorError("bad_request", "Record an outcome before closing the task.")
    c = db.conn()
    with c:
        c.execute(
            "UPDATE tasks SET status = COALESCE(?, status), outcome = COALESCE(?, outcome), outcome_units = COALESCE(?, outcome_units), "
            "outcome_note = COALESCE(?, outcome_note), assignee = COALESCE(?, assignee), updated_at = ? WHERE task_id = ?",
            (status or None, outcome or None, outcome_units, note or None, assignee or None, _now(), task_id),
        )
        parts = [x for x in (status and f"status → {status}", outcome and f"outcome: {outcome}", outcome_units is not None and f"{outcome_units} units") if x]
        _event(task_id, actor, "; ".join(parts) or "updated", note)
    return get_task(task_id)
