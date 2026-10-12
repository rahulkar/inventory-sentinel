"""Triage decisions from warehouse teams, stored append-only per dataset and keyed by the stable alert key."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app import config
from app.schemas import SimulateTriageRequest, TriageSummary

_lock = threading.Lock()
TRUTH_TO_OUTCOME = {
    "theft_external": "confirmed_theft", "theft_internal": "confirmed_theft", "scan_fraud": "confirmed_theft",
    "counting_error": "counting_error", "receiving_error": "process_issue", "data_entry_error": "process_issue",
    "velocity_shift": "process_issue", "none": "false_alarm", "": "false_alarm",
}


def _path(dataset_id: str):
    return config.TRIAGE_DIR / f"{dataset_id}.jsonl"


def all_records(dataset_id: str) -> list[dict[str, Any]]:
    p = _path(dataset_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def latest(dataset_id: str) -> dict[str, dict[str, Any]]:
    """alert_key -> the latest decision."""
    out: dict[str, dict[str, Any]] = {}
    for r in all_records(dataset_id):
        out[r["alert_key"]] = r
    return out


def append(dataset_id: str, records: list[dict[str, Any]]) -> None:
    config.ensure_dirs()
    with _lock, _path(dataset_id).open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def reset(dataset_id: str) -> int:
    n = len(all_records(dataset_id))
    p = _path(dataset_id)
    if p.exists():
        p.unlink()
    return n


def _record(row: dict[str, Any], run_id: str, outcome: str, note: str | None, source: str, decided_at: str) -> dict[str, Any]:
    return {
        "alert_key": row["alert_key"], "run_id": run_id, "alert_id": row["alert_id"], "store_id": str(row["store_id"]), "sku_id": str(row["sku_id"]),
        "start_date": row["start_date"], "end_date": row["end_date"], "likely_type": row["likely_type"], "severity": row["severity"],
        "warehouse_team": row.get("warehouse_team", ""), "outcome": outcome, "note": note, "source": source, "decided_at": decided_at,
    }


def decide(run_id: str, alert_ids: list[str], outcome: str, note: str | None) -> list[dict[str, Any]]:
    from app.services import storage

    rd = storage.load_run(run_id)
    df = rd.incidents
    rows = df[df["alert_id"].isin(alert_ids)].to_dict("records")
    if not rows:
        raise LookupError("Alert not found in this run.")
    now = datetime.now().replace(microsecond=0).isoformat()
    recs = [_record(r, run_id, outcome, note, "user", now) for r in rows]
    append(rd.run.dataset_id, recs)
    return recs


def simulate(req: SimulateTriageRequest) -> dict[str, Any]:
    """Synthetic datasets only: review the top open alerts from the history window using the answer key, with noise."""
    from app.services import storage

    rd = storage.load_run(req.run_id)
    ds = storage.load_dataset(rd.run.dataset_id)
    if not ds.truth:
        raise ValueError("Simulated triage needs the synthetic answer key; review alerts by hand on real data.")
    df = rd.incidents
    done = latest(ds.meta.id)
    hist = df[(df["start_date"] < ds.meta.test_from_date) & (~df["alert_key"].isin(done))]
    hist = hist.sort_values(["p_true", "value_at_risk_gbp"], ascending=False)
    rng = np.random.default_rng(len(done) + 7)
    # teams work the top of the queue but also spot-check further down (that is where false alarms show up)
    n_total = req.days * req.per_day
    n_top = int(round(n_total * 0.7))
    top = hist.iloc[:n_top]
    rest = hist.iloc[n_top:]
    spot = rest.sample(n=min(len(rest), n_total - len(top)), random_state=int(rng.integers(1_000_000))) if len(rest) else rest
    hist = pd.concat([top, spot]).sample(frac=1.0, random_state=int(rng.integers(1_000_000)))
    start = datetime.fromisoformat(ds.meta.test_from_date) - timedelta(days=req.days)
    if done:
        prev = max(r["decided_at"] for r in done.values())
        start = max(start, datetime.fromisoformat(prev[:19]) + timedelta(days=1))
    recs = []
    pos = 0
    rows = hist.to_dict("records")
    for d in range(req.days):
        day = (start + timedelta(days=d)).replace(hour=17, minute=0, second=0).isoformat()
        for r in rows[pos : pos + req.per_day]:
            outcome = TRUTH_TO_OUTCOME.get(str(r.get("truth_type") or "none"), "false_alarm")
            if rng.random() < req.noise:
                outcome = str(rng.choice([o for o in config.TRIAGE_OUTCOMES if o != outcome]))
            recs.append(_record(r, req.run_id, outcome, "simulated review", "simulated", day))
        pos += req.per_day
    append(ds.meta.id, recs)
    true = sum(r["outcome"] != "false_alarm" for r in recs)
    return {"reviewed": len(recs), "true_alerts": true, "precision": round(true / max(len(recs), 1), 4)}


def summary(dataset_id: str, run_id: str | None) -> TriageSummary:
    recs = list(latest(dataset_id).values())
    reviewed = len(recs)
    true = sum(r["outcome"] != "false_alarm" for r in recs)
    open_alerts = 0
    if run_id:
        from app.services import storage

        try:
            df = storage.load_run(run_id).incidents
            keys = set(r["alert_key"] for r in recs)
            open_alerts = int((~df["alert_key"].isin(keys)).sum()) if len(df) else 0
        except LookupError:
            pass

    def group(key: str) -> list[dict[str, Any]]:
        g: dict[str, list[int]] = {}
        for r in recs:
            k = str(r.get(key) or "unknown")[:10] if key == "decided_at" else str(r.get(key) or "unknown")
            g.setdefault(k, [0, 0])
            g[k][0] += 1
            g[k][1] += int(r["outcome"] != "false_alarm")
        return [{"key": k, "reviewed": v[0], "true": v[1], "precision": round(v[1] / v[0], 4)} for k, v in sorted(g.items())]

    matrix: dict[tuple[str, str], int] = {}
    for r in recs:
        matrix[(r["likely_type"], r["outcome"])] = matrix.get((r["likely_type"], r["outcome"]), 0) + 1
    can = reviewed >= config.RETRAIN_MIN_REVIEWED and true >= config.RETRAIN_MIN_EACH and (reviewed - true) >= config.RETRAIN_MIN_EACH
    reason = None if can else f"Needs at least {config.RETRAIN_MIN_REVIEWED} reviewed alerts with {config.RETRAIN_MIN_EACH}+ real problems and {config.RETRAIN_MIN_EACH}+ false alarms (now {reviewed}: {true} real, {reviewed - true} false)."
    return TriageSummary(
        dataset_id=dataset_id, run_id=run_id, reviewed=reviewed, true_alerts=true, false_alarms=reviewed - true,
        precision=round(true / reviewed, 4) if reviewed else None, open_alerts=open_alerts, simulated=sum(r.get("source") == "simulated" for r in recs),
        by_day=group("decided_at"), by_type=group("likely_type"), by_severity=group("severity"), by_team=group("warehouse_team"),
        matrix=[{"likely_type": a, "outcome": b, "count": c} for (a, b), c in sorted(matrix.items())], can_retrain=can, retrain_reason=reason,
    )
