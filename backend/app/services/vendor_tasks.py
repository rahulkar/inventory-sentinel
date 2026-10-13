"""Vendor tasks: approved actions Sentinel writes back to a vendor's system (recounts, investigations, audits).

Nothing here runs on its own. Every task comes from a person: an approved chat or scheduler proposal, or the confirm
dialog in the alert drill-down. Sentinel keeps its own record in data/vendor_tasks.jsonl (append-only; the latest line
per task wins). Each sync reads status changes back, and a closed task's outcome becomes team feedback (triage) for
the connector.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any

from app import config
from app.schemas import Connector, VendorTask, VendorTaskDraft
from app.services import connectors, detection, storage, triage

_lock = threading.RLock()
THEFT_TYPES = {"theft_external", "theft_internal", "scan_fraud"}
DEFAULT_TYPE_BY_LIKELY = {
    "theft_external": "cctv_review", "theft_internal": "investigate", "scan_fraud": "till_audit", "counting_error": "recount",
    "receiving_error": "receiving_check", "data_entry_error": "data_correction", "velocity_shift": "recount", "unclear": "recount",
}
PRIORITY_BY_SEVERITY = {"critical": "urgent", "high": "high", "medium": "normal"}
DUE_HOURS_BY_PRIORITY = {"urgent": 4, "high": 24, "normal": 72, "low": 168}


def outcome_to_triage(outcome: str | None, likely_type: str | None) -> str | None:
    """Vendor task outcome -> triage outcome (None = no feedback, e.g. a rejected task)."""
    if outcome == "confirmed_loss":
        return "confirmed_theft" if likely_type in THEFT_TYPES else "process_issue"
    return {"count_corrected": "counting_error", "process_fixed": "process_issue", "no_issue": "false_alarm"}.get(outcome or "")


# ---------------------------------------------------------------- local record
def _all() -> dict[str, VendorTask]:
    out: dict[str, VendorTask] = {}
    p = config.VENDOR_TASKS_PATH
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            t = VendorTask(**json.loads(line))
        except ValueError:
            continue
        out[f"{t.connector_id}:{t.task_id}"] = t
    return out


def _append(items: list[VendorTask]) -> None:
    if not items:
        return
    config.ensure_dirs()
    with _lock, config.VENDOR_TASKS_PATH.open("a", encoding="utf-8") as fh:
        for t in items:
            fh.write(t.model_dump_json() + "\n")


def list_tasks(connector_id: str | None = None, status: str | None = None, store_id: str | None = None, alert_key: str | None = None, run_id: str | None = None, limit: int = 200) -> list[VendorTask]:
    with _lock:
        items = list(_all().values())
    if connector_id:
        items = [t for t in items if t.connector_id == connector_id]
    if status == "open":
        items = [t for t in items if t.status not in ("done", "rejected")]
    elif status:
        items = [t for t in items if t.status == status]
    if store_id:
        items = [t for t in items if t.store_id == store_id]
    if alert_key:
        items = [t for t in items if t.alert_key == alert_key]
    if run_id:
        items = [t for t in items if t.run_id == run_id]
    items.sort(key=lambda t: t.updated_at, reverse=True)
    return items[:limit]


def for_alert(alert_key: str) -> list[VendorTask]:
    return list_tasks(alert_key=alert_key)


def open_count(connector_id: str) -> int:
    return len(list_tasks(connector_id=connector_id, status="open", limit=100_000))


# ---------------------------------------------------------------- creating
def connector_for_run(run_id: str) -> Connector:
    rd = storage.load_run(run_id)
    meta = storage.get_dataset_meta(rd.run.dataset_id)
    conn_id = (meta.params or {}).get("connector_id") if meta else None
    if not conn_id:
        raise ValueError("This run is on an imported dataset, which has no vendor connector to send tasks to.")
    return connectors.get(conn_id)


def draft_for_alert(run_id: str, alert_id: str, type_: str | None = None, sop_step: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fill a task from an alert (and optionally an SOP step's vendor_task template)."""
    from app.services import sops

    a = detection.get_alert(run_id, alert_id)
    tmpl = (sop_step or {}).get("vendor_task") or {}
    t = type_ or tmpl.get("type") or DEFAULT_TYPE_BY_LIKELY.get(a.likely_type, "recount")
    priority = tmpl.get("priority") or PRIORITY_BY_SEVERITY.get(a.severity, "normal")
    fields = sops.alert_fields(a)
    title = sops.fill(tmpl.get("title") or "{type_label}: {sku_name} at {store_name}", {**fields, "type_label": t.replace("_", " ").capitalize()})
    desc = sops.fill(tmpl.get("description") or (
        "Inventory Sentinel flagged {sku_name} ({sku_id}) at {store_name} from {start_date} to {end_date}: about {units_at_risk} units "
        "(£{value_at_risk_gbp}) unexplained, pattern consistent with {likely_label}. Reasons: {reasons}."
    ), fields)
    return {"alert": a, "type": t, "priority": priority, "title": title[:200], "description": desc[:4000]}


def create(drafts: list[VendorTaskDraft], source: str = "ui", connector_id: str | None = None) -> dict[str, Any]:
    """Raise approved tasks in the vendor system (one MCP session per connector). Returns {created, existing, failed}."""
    from app.services import sops

    created: list[VendorTask] = []
    existing: list[VendorTask] = []
    failed: list[dict[str, Any]] = []
    prepared: dict[str, tuple[Connector, list[tuple[VendorTaskDraft, VendorTask, dict[str, Any]]]]] = {}
    for d in drafts:
        try:
            conn = connectors.get(connector_id) if connector_id else connector_for_run(d.run_id)
            caps = conn.capabilities or {}
            step = sops.step(d.sop_id, d.sop_step) if d.sop_id and d.sop_step else None
            filled = draft_for_alert(d.run_id, d.alert_id, d.type, step)
            a = filled["alert"]
            task_type = filled["type"]
            if caps.get("task_types") and task_type not in caps["task_types"]:
                raise ValueError(f"{conn.name} does not accept '{task_type}' tasks (it takes {', '.join(caps['task_types'])}).")
            priority = d.priority or filled["priority"]
            title = d.title or filled["title"]
            description = (d.description or filled["description"]) + (f"\n\nNote from Sentinel: {d.note}" if d.note else "")
            due = (datetime.now() + timedelta(hours=float((step or {}).get("due_hours") or DUE_HOURS_BY_PRIORITY.get(priority, 72)))).replace(microsecond=0).isoformat()
            sop_id = d.sop_id or sops.sop_id_for_type(a.likely_type)
            args = {
                "type": task_type, "store_id": a.store_id, "sku_id": a.sku_id, "title": title, "description": description,
                "priority": priority, "idempotency_key": f"{a.alert_key}:{task_type}", "external_ref": a.alert_key, "source_alert_id": a.alert_id,
                "sop_id": sop_id, "due_by": due,
                "evidence": {"severity": a.severity, "dates": f"{a.start_date} to {a.end_date}", "units_at_risk": a.units_at_risk, "value_at_risk_gbp": a.value_at_risk_gbp, "likely_type": a.likely_type, "p_true": a.p_true, "run_id": d.run_id},
            }
            now = storage.now_iso()
            rec = VendorTask(
                task_id="pending", connector_id=conn.id, alert_key=a.alert_key, alert_id=a.alert_id, run_id=d.run_id, store_id=a.store_id, sku_id=a.sku_id,
                type=task_type, priority=priority, title=title, sop_id=sop_id, sop_step=d.sop_step, source=source, created_at=now, updated_at=now,
                alert={"start_date": a.start_date, "end_date": a.end_date, "likely_type": a.likely_type, "severity": a.severity, "warehouse_team": a.warehouse_team},
            )
            prepared.setdefault(conn.id, (conn, []))[1].append((d, rec, args))
        except (connectors.ConnectorError, LookupError, ValueError) as exc:
            failed.append({"alert_id": d.alert_id, "run_id": d.run_id, "type": d.type, "error": str(exc)})
    for conn, items in prepared.values():
        try:
            results = connectors.call_each(conn, [("create_task", args) for _, _, args in items])
        except connectors.ConnectorError as exc:
            failed += [{"alert_id": d.alert_id, "run_id": d.run_id, "type": rec.type, "error": str(exc)} for d, rec, _ in items]
            continue
        for (d, rec, _), res in zip(items, results):
            if isinstance(res, BaseException):
                failed.append({"alert_id": d.alert_id, "run_id": d.run_id, "type": rec.type, "error": str(res)})
                continue
            rec = rec.model_copy(update={"task_id": res["task_id"], "status": res.get("status", "open"), "created_at": res.get("created_at") or rec.created_at})
            if res.get("created", True):
                created.append(rec)
                _append([rec])
                continue
            prior = _all().get(f"{conn.id}:{rec.task_id}")
            existing.append(prior or rec)
            if prior is None:
                _append([rec])
    return {"created": [t.model_dump() for t in created], "existing": [t.model_dump() for t in existing], "failed": failed}


# ---------------------------------------------------------------- reading outcomes back
def refresh(conn: Connector) -> int:
    """Pull status changes for tasks Sentinel raised; record closed outcomes as team feedback. Returns updates applied."""
    with _lock:
        mine = {t.task_id: t for t in _all().values() if t.connector_id == conn.id}
    if not mine:
        return 0
    live = [t.updated_at for t in mine.values() if t.status not in ("done", "rejected")]
    pending_feedback = [t for t in mine.values() if t.status == "done" and not t.feedback_recorded and conn.feedback_from_tasks]
    if not live and not pending_feedback:
        return 0
    since = min(live)[:10] if live and not pending_feedback else None  # whole days: tolerate clock skew between the two systems
    updates: list[VendorTask] = []
    cursor = None
    while True:
        pg = connectors.call(conn, "list_tasks", {"updated_since": since, "cursor": cursor, "page_size": 500})
        for it in pg.get("items", []):
            t = mine.get(it.get("task_id"))
            if t is None:
                continue
            changed = (it.get("status"), it.get("outcome"), it.get("outcome_units"), it.get("outcome_note")) != (t.status, t.outcome, t.outcome_units, t.outcome_note)
            if changed:
                t = t.model_copy(update={"status": it.get("status") or t.status, "outcome": it.get("outcome"), "outcome_units": it.get("outcome_units"), "outcome_note": it.get("outcome_note"), "updated_at": it.get("updated_at") or storage.now_iso()})
            if t.status == "done" and t.outcome and not t.feedback_recorded and conn.feedback_from_tasks and t.alert_key:
                _feedback(conn, t)
                t = t.model_copy(update={"feedback_recorded": True})
                changed = True
            if changed:
                updates.append(t)
                mine[t.task_id] = t
        cursor = pg.get("next_cursor")
        if not cursor:
            break
    _append(updates)
    return len(updates)


def _feedback(conn: Connector, t: VendorTask) -> None:
    outcome = outcome_to_triage(t.outcome, t.alert.get("likely_type"))
    if outcome is None:
        return
    note = f"vendor task {t.task_id} ({t.type}): {t.outcome}" + (f", {t.outcome_units} units" if t.outcome_units is not None else "") + (f". {t.outcome_note}" if t.outcome_note else "")
    triage.append(conn.id, [{
        "alert_key": t.alert_key, "run_id": t.run_id, "alert_id": t.alert_id, "store_id": t.store_id, "sku_id": t.sku_id or "",
        "start_date": t.alert.get("start_date"), "end_date": t.alert.get("end_date"), "likely_type": t.alert.get("likely_type"), "severity": t.alert.get("severity"),
        "warehouse_team": t.alert.get("warehouse_team", ""), "outcome": outcome, "note": note[:500], "source": "vendor_task", "decided_at": storage.now_iso(),
    }])
