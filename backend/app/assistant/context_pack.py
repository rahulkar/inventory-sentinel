"""The 'current state' block injected into every agent instruction: what is loaded and what the user is looking at."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from app import config
from app.assistant import plain_language as pl
from app.services import jobs, storage, triage

PAGE_BLURBS = {
    "overview": "Overview: the three steps (Data, Train, Act), latest detection KPIs and the top alerts.",
    "story": "How it works: the leadership story with live figures (Present mode).",
    "data": "Data: vendor connectors (MCP URL + token, test, sync now, last sync and warnings) and manual CSV import; preview the snapshots' daily rows, stores, SKUs and loss-prevention flags.",
    "schedules": "Schedules: timed pipelines (sync a vendor, use or retrain a model of the user's choice, detect, propose vendor tasks), their run history and the vendor-task approvals waiting from scheduled runs.",
    "train": "Train: pick detection methods, train them on the vendor's own history and compare how well each finds real problems (loss-prevention flags, team feedback, or a demo vendor's answer key).",
    "act": "Act: Alerts, Dashboard, Investigation planner, Drill-down (with the alert's SOP checklist and 'Raise vendor task' buttons) and Triage tabs for a detection run.",
    "models": "Models: every trained model with metrics, thresholds, drivers and export (bundle / ONNX).",
    "experiments": "Experiments: every training run with its leaderboard.",
    "assistant": "Assistant: the full chat page with conversations and the team's usage and cost.",
    "settings": "Settings: the LiteLLM gateway connection for this assistant.",
    "alerts": "Alerts (executive view): the open alerts with store, item, likely type, severity and money at risk; click one for the reasons and its stock story.",
    "plan": "Plan (executive view): investigator hours slider, alerts worked, expected recovery, return on cost and the top of the work list.",
}
EXEC_BLURBS = {
    "overview": "Executive overview: three headline numbers (stock value at risk, alerts worth a visit with expected recovery and return, how much better machine learning ranks real problems than the rule of thumb), a store x category heatmap and the five alerts to work first. If nothing has run yet it shows one 'Run the whole pipeline' button.",
}


class UiState(BaseModel):
    page: str = "overview"
    mode: str = "analyst"  # "exec" when the app is in executive mode (CIO/CTO audience)
    tab: str | None = None
    selected_dataset_id: str | None = None
    selected_run_id: str | None = None
    selected_alert_id: str | None = None
    drill_store_id: str | None = None
    drill_sku_id: str | None = None
    active_model_id: str | None = None
    selected_schedule_id: str | None = None


def _m(m: Any) -> dict[str, Any]:
    x = m.metrics
    return {
        "model_id": m.model_id, "method": m.label, "key": m.key, "dataset": m.dataset_name, "in_use": m.is_active,
        "average_precision": x.average_precision, "precision_at_1000": x.precision_at_k, "incident_recall": x.incident_recall,
        "value_captured_pct": x.value_captured_pct, "label_source": x.label_source, "engine": m.engine, "created_at": m.created_at,
    }


def build_context_pack(ui: UiState, session_id: str | None) -> dict[str, Any]:
    datasets = storage.list_datasets()
    models = storage.list_models()
    active_id = storage.get_active_model_id()
    runs = storage.list_runs()
    sel_ds = next((d for d in datasets if d.id == ui.selected_dataset_id), None) or (datasets[0] if datasets else None)
    pack: dict[str, Any] = {
        "today": date.today().isoformat(),
        "page": ui.page,
        "page_blurb": (EXEC_BLURBS.get(ui.page) if ui.mode == "exec" else None) or PAGE_BLURBS.get(ui.page, ""),
        "audience": (
            "executive (CIO/CTO): keep it short, plain and about money, risk and the next action. Their menu has only Overview, Alerts, "
            "Plan (the investigation planner) and Story; point to those, not to Data, Train, Act, Models or Experiments (an Analyst switch top right shows those)"
        ) if ui.mode == "exec" else "analyst",
        "tab": ui.tab,
        "datasets": [
            {"dataset_id": d.id, "name": d.name, "kind": d.kind, "rows": d.n_rows, "stores": d.n_stores, "skus": d.n_skus, "days": d.n_days,
             "dates": f"{d.date_start} to {d.date_end}", "evaluation_window_from": d.test_from_date, "answer_key": d.has_truth, "lp_flags": d.n_lp_flags, "injected_incidents": d.n_incidents,
             "connector": (d.params or {}).get("connector_name")}
            for d in datasets[:5]
        ],
        "selected_dataset_id": sel_ds.id if sel_ds else None,
        "models": [_m(m) for m in sorted(models, key=lambda m: -(m.metrics.average_precision or -1))[:6]],
        "baseline_ap": next((m.metrics.average_precision for m in models if m.key == "zscore" and (not sel_ds or m.dataset_id == sel_ds.id)), None),
    }
    act = storage.get_model(active_id) if active_id else None
    if act:
        pack["active_model"] = {
            "model_id": act.model_id, "method": act.label, "dataset": act.dataset_name, "alert_rate": act.alert_rate,
            "thresholds": act.thresholds.model_dump(), "top_drivers": [{"feature": i.feature, "label": pl.FEATURE_LABELS.get(i.feature, i.feature), "share": i.importance} for i in act.importances[:5]],
            "calibration_source": act.calibration.source, "engine": act.engine, "parent_model_id": act.parent_model_id,
        }
    pack["runs"] = [
        {"run_id": r.run_id, "model": r.model_label, "model_id": r.model_id, "model_in_use": r.model_in_use, "dataset": r.dataset_name, "incidents": r.incidents, "value_at_risk_gbp": r.value_at_risk_gbp, "created_at": r.created_at}
        for r in runs[:4]
    ]
    run_id = ui.selected_run_id or (runs[0].run_id if runs else None)
    pack["selected_run_id"] = run_id
    if run_id:
        try:
            rd = storage.load_run(run_id)
            k = rd.run.kpis
            pack["selected_run"] = {
                "run_id": run_id, "model": rd.run.model_label, "model_in_use": rd.run.model_id == active_id, "incidents": k.incidents, "value_at_risk_gbp": k.value_at_risk_gbp,
                "by_severity": k.by_severity, "by_type": k.by_type, "stores_affected": k.stores_affected,
                "evaluation": rd.run.evaluation.model_dump() if rd.run.evaluation else None,
                "top_stores": rd.aggregates.get("top_stores", [])[:3], "top_categories": rd.aggregates.get("by_category", [])[:3],
            }
            ts = triage.summary(rd.run.dataset_id, run_id)
            pack["triage"] = {"reviewed": ts.reviewed, "precision": ts.precision, "open_alerts": ts.open_alerts, "simulated": ts.simulated, "can_retrain": ts.can_retrain}
        except LookupError:
            pass
    if ui.selected_alert_id:
        pack["selected_alert_id"] = ui.selected_alert_id
    if ui.drill_store_id and ui.drill_sku_id:
        pack["drilldown"] = {"store_id": ui.drill_store_id, "sku_id": ui.drill_sku_id}
    pack["active_jobs"] = [{"job_id": j.job_id, "title": j.title, "status": j.status, "percent": round(j.percent), "eta_seconds": j.eta_seconds} for j in jobs.list_jobs(active_only=True, limit=5)]
    from app.assistant import proposals

    pack["proposals"] = [{"proposal_id": p.proposal_id, "title": p.title, "status": p.status, "job_id": p.job_id} for p in proposals.list_for_session(session_id, limit=5)] if session_id else []
    pack["planner_defaults"] = config.PLANNER_DEFAULTS
    pack.update(_ops(ui))
    return pack


def _ops(ui: UiState) -> dict[str, Any]:
    """Connectors, schedules and approvals waiting (never tokens)."""
    from app.assistant import proposals
    from app.services import connectors, scheduler, vendor_tasks

    out: dict[str, Any] = {"connectors": [], "schedules": []}
    for c in connectors.list_all()[:5]:
        caps = c.capabilities or {}
        last = c.last_sync
        out["connectors"].append({
            "connector_id": c.id, "name": c.name, "enabled": c.enabled, "vendor": (caps.get("vendor") or {}).get("name"),
            "last_sync": f"{last.status} at {last.at}" + (f", data through {last.synced_through}" if last.synced_through else "") + (f", error: {last.error}" if last.error else "") if last else "never synced",
            "warnings": (last.warnings if last else [])[:2], "answer_key": bool((caps.get("features") or {}).get("answer_key")), "open_vendor_tasks": vendor_tasks.open_count(c.id),
        })
    for sc in scheduler.list_all()[:6]:
        lr = sc.last_run or {}
        out["schedules"].append({
            "schedule_id": sc.id, "name": sc.name, "enabled": sc.enabled, "summary": scheduler.describe(sc), "next_run_at_utc": sc.next_run_at,
            "last_run": f"{lr.get('status')} ({lr.get('trigger')}) at {lr.get('finished_at') or lr.get('started_at')}" + (f", {lr.get('new_alerts')} new alerts" if lr.get("new_alerts") is not None else "") + (f", error: {lr.get('error')}" if lr.get("error") else "") if lr else "never ran",
        })
    out["scheduler_approvals_waiting"] = [{"proposal_id": p.proposal_id, "title": p.title} for p in proposals.list_pending(source="scheduler", limit=5)]
    if ui.selected_schedule_id:
        out["selected_schedule_id"] = ui.selected_schedule_id
    return out


def render_context_pack(p: dict[str, Any]) -> str:
    lines = [f"Today: {p['today']}. User is on: {p['page_blurb'] or p['page']}" + (f" (tab: {p['tab']})" if p.get("tab") else ""), f"Audience: {p.get('audience', 'analyst')}."]
    if p["datasets"]:
        lines.append("Datasets:")
        for d in p["datasets"]:
            src = f"snapshot of {d['connector']}" if d.get("connector") else d["kind"]
            lines.append(f"  - {d['dataset_id']} '{d['name']}' ({src}): {d['rows']:,} rows ({d['stores']} stores x {d['skus']} SKUs x {d['days']} days, {d['dates']}), evaluation window from {d['evaluation_window_from']}, answer key: {('yes (demo vendor)' if d['kind'] == 'connector' else 'yes (synthetic)') if d['answer_key'] else 'no'}, {d['lp_flags']} loss-prevention flags")
    else:
        lines.append("Datasets: none yet (propose a sync of a vendor connector, or import a CSV on the Data page).")
    if p.get("connectors"):
        lines.append("Vendor connectors (MCP):")
        for c in p["connectors"]:
            lines.append(f"  - {c['connector_id']} '{c['name']}'{'' if c['enabled'] else ' [OFF]'}: last sync {c['last_sync']}; {c['open_vendor_tasks']} open vendor tasks" + (f"; warnings: {' | '.join(c['warnings'])}" if c["warnings"] else ""))
    else:
        lines.append("Vendor connectors: none (the user adds one on the Data page).")
    if p.get("schedules"):
        lines.append("Schedules:")
        for sc in p["schedules"]:
            lines.append(f"  - {sc['schedule_id']} '{sc['name']}'{'' if sc['enabled'] else ' [paused]'}: {sc['summary']}; next {sc['next_run_at_utc']} UTC; last run {sc['last_run']}")
    if p.get("scheduler_approvals_waiting"):
        lines.append("Waiting for approval from scheduled runs: " + "; ".join(f"{x['proposal_id']} {x['title']}" for x in p["scheduler_approvals_waiting"]))
    if p["models"]:
        lines.append("Models (best average precision first; baseline = rule of thumb):")
        for m in p["models"]:
            lines.append(f"  - {m['model_id']} {m['method']}{' [IN USE]' if m['in_use'] else ''}: AP {m['average_precision']}, precision@1000 {m['precision_at_1000']}, incidents caught {m['incident_recall']}, value captured {m['value_captured_pct']}% ({m['label_source']}, engine {m['engine']})")
    else:
        lines.append("Models: none trained yet.")
    a = p.get("active_model")
    if a:
        drivers = ", ".join(f"{d['label']} {d['share']:.0%}" for d in a["top_drivers"])
        lines.append(f"Model in use: {a['method']} ({a['model_id']}); alert rate {a['alert_rate']:.1%}; P(true) calibrated from {a['calibration_source']}; top drivers: {drivers}.")
    if p["runs"]:
        lines.append("Detection runs (newest first):")
        for r in p["runs"]:
            lines.append(f"  - {r['run_id']}: {r['incidents']:,} alerts, £{r['value_at_risk_gbp']:,.0f} at risk, by {r['model']} ({'model in use' if r['model_in_use'] else 'NOT the model in use'})")
    s = p.get("selected_run")
    if s:
        ev = s.get("evaluation") or {}
        lines.append(f"Selected run {s['run_id']}: severity {s['by_severity']}, likely types {s['by_type']}, {s['stores_affected']} stores affected" + (f"; on the evaluation window it caught {ev.get('incident_recall') or 0:.0%} of injected incidents with {ev.get('alert_precision') or 0:.0%} of alerts real (demo vendor's answer key)" if ev else "") + ".")
        if s.get("top_stores"):
            lines.append("  Top stores by £ at risk: " + "; ".join(f"{x['label']} £{x['value_gbp']:,.0f} ({x['alerts']} alerts)" for x in s["top_stores"]))
    t = p.get("triage")
    if t:
        lines.append(f"Triage: {t['reviewed']} alerts reviewed ({t['simulated']} simulated), precision {t['precision']}, {t['open_alerts']} open; retrain with feedback {'possible' if t['can_retrain'] else 'not yet possible'}.")
    if p.get("selected_alert_id"):
        lines.append(f"The user has alert {p['selected_alert_id']} open.")
    if p.get("drilldown"):
        lines.append(f"The user is drilling into store {p['drilldown']['store_id']} / SKU {p['drilldown']['sku_id']}.")
    if p["active_jobs"]:
        lines.append("Jobs running/queued: " + "; ".join(f"{j['job_id']} {j['title']} ({j['status']}, {j['percent']}%)" for j in p["active_jobs"]))
    if p["proposals"]:
        lines.append("Proposals in this conversation: " + "; ".join(f"{x['proposal_id']} {x['title']} ({x['status']})" for x in p["proposals"]))
    d = p["planner_defaults"]
    lines.append(f"Planner defaults: {d['hours']:.0f} investigator hours at £{d['hourly_cost']:.0f}/hour, recovery rate {d['recovery_rate']:.0%}, horizon {d['horizon_days']:.0f} days.")
    return "\n".join(lines)
