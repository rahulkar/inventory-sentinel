"""SQLite storage for the demo vendor: WAL mode, one connection per thread."""
from __future__ import annotations

import sqlite3
import threading
from typing import Any

from vendor_mock import settings
from vendor_mock.sim.constants import MEASURES

_local = threading.local()

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS stores (
    store_code INTEGER PRIMARY KEY, store_id TEXT UNIQUE NOT NULL, store_name TEXT, region TEXT, format TEXT, size_band TEXT,
    warehouse_team TEXT, footfall_index REAL, opens_at TEXT, closes_at TEXT
);
CREATE TABLE IF NOT EXISTS skus (
    sku_code INTEGER PRIMARY KEY, sku_id TEXT UNIQUE NOT NULL, sku_name TEXT, category TEXT, unit_cost REAL, unit_price REAL,
    high_theft_risk INTEGER, security_tagged INTEGER
);
CREATE TABLE IF NOT EXISTS daily (
    day INTEGER NOT NULL, store_code INTEGER NOT NULL, sku_code INTEGER NOT NULL,
    {", ".join(f"{m} INTEGER" for m in MEASURES)},
    PRIMARY KEY (day, store_code, sku_code)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS answer_key (
    day INTEGER NOT NULL, store_code INTEGER NOT NULL, sku_code INTEGER NOT NULL, truth_type TEXT, truth_incident INTEGER, truth_loss_units INTEGER,
    PRIMARY KEY (day, store_code, sku_code)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS lp_flags (
    flag_id TEXT PRIMARY KEY, day INTEGER, store_code INTEGER, sku_code INTEGER, flag_type TEXT, source TEXT, confirmed INTEGER,
    loss_value_gbp REAL, reported_day INTEGER
);
CREATE INDEX IF NOT EXISTS lp_flags_day ON lp_flags(day);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, type TEXT, status TEXT, priority TEXT, title TEXT, description TEXT,
    store_id TEXT, sku_id TEXT, external_ref TEXT, source_alert_id TEXT, sop_id TEXT, evidence_json TEXT, due_by TEXT,
    created_at TEXT, updated_at TEXT, assignee TEXT, outcome TEXT, outcome_units INTEGER, outcome_note TEXT
);
CREATE INDEX IF NOT EXISTS tasks_updated ON tasks(updated_at);
CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, at TEXT, actor TEXT, event TEXT, note TEXT
);
"""


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(settings.DB_PATH, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        _local.conn = c
    return c


def init() -> None:
    conn().executescript(SCHEMA)
    conn().commit()


def close() -> None:
    c = getattr(_local, "conn", None)
    if c is not None:
        c.close()
        _local.conn = None


def get_meta(key: str, default: str | None = None) -> str | None:
    row = conn().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key: str, value: Any) -> None:
    c = conn()
    c.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
    c.commit()
