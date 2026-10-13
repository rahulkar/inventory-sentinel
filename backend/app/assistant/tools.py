"""The tool catalogue shared by the ADK agents and the MCP server.

Every tool is a plain synchronous function with JSON-only arguments and a JSON-serialisable dict result containing
"status": "ok" | "error". Outputs are compact (rows capped, numbers rounded). Google-style docstrings matter: both ADK
and MCP show them to the model.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from app import config
from app.assistant import knowledge
from app.assistant import plain_language as pl
from app.assistant import proposals
from app.assistant.context_pack import UiState, build_context_pack
from app.schemas import PlanRequest
from app.services import connectors, detection, jobs, planner, registry, scheduler, sops, storage, training, triage, vendor_tasks

ROW_CAP = config.ASSISTANT_TOOL_ROW_CAP


def _ok(**kw: Any) -> dict[str, Any]:
    return {"status": "ok", **kw}


def _err(message: str) -> dict[str, Any]:
    return {"status": "error", "error_message": message}


def _jsonable(obj: Any) -> Any:
    def conv(o: Any) -> Any:
        if isinstance(o, np.floating):
            return round(float(o), 4)
        if isinstance(o, np.integer):
            return int(o)
        return str(o)

    return json.loads(json.dumps(obj, default=conv))


def _dataset(dataset_id: str | None):
    if dataset_id:
        return storage.get_dataset_meta(dataset_id)
    ds = storage.list_datasets()
    return ds[0] if ds else None


def _run_id(run_id: str | None) -> str | None:
    if run_id:
        return run_id
    runs = storage.list_runs()
    in_use = [r for r in runs if r.model_in_use]
    return (in_use or runs)[0].run_id if runs else None


def _run_note(run_id: str) -> dict[str, Any]:
    rd = storage.load_run(run_id)
    active = storage.get_active_model_id()
    in_use = rd.run.model_id == active
    return {
        "run_id": run_id, "model": rd.run.model_label, "model_id": rd.run.model_id, "model_in_use": in_use,
        "model_note": "Produced by the model in use." if in_use else f"Produced by {rd.run.model_label} ({rd.run.model_id}), which is NOT the model in use; say so and offer to run detection with the model in use.",
    }


# ---------------------------------------------------------------- datasets
def list_datasets() -> dict[str, Any]:
    """List the inventory datasets (newest first): vendor snapshots (kind "connector", one per sync) and manual imports, with size, date range, loss-prevention flag counts and whether a demo vendor answer key came with them."""
    ds = storage.list_datasets()[:ROW_CAP]
    return _ok(count=len(ds), datasets=[{
        "dataset_id": d.id, "name": d.name, "kind": d.kind, "rows": d.n_rows, "stores": d.n_stores, "skus": d.n_skus, "days": d.n_days,
        "date_start": d.date_start, "date_end": d.date_end, "evaluation_window_from": d.test_from_date, "answer_key": d.has_truth,
        "injected_incidents": d.n_incidents, "lp_flags": d.n_lp_flags, "size_mb": round(d.size_bytes / 1e6, 1), "created_at": d.created_at,
        "connector": (d.params or {}).get("connector_name"), "synced_through": (d.params or {}).get("synced_through"),
    } for d in ds])


def describe_dataset(dataset_id: str | None = None) -> dict[str, Any]:
    """Describe a dataset: columns with plain labels, key statistics, rows by category, net stock gap, import mapping and warnings.

    Args:
        dataset_id: Dataset id (ds_...). Defaults to the dataset selected in the app, else the most recent.
    """
    d = _dataset(dataset_id)
    if d is None:
        return _err("No dataset yet. Sync a vendor connector (propose a sync job) or import a CSV on the Data page.")
    st = d.stats
    return _ok(
        dataset_id=d.id, name=d.name, kind=d.kind, rows=d.n_rows, stores=d.n_stores, skus=d.n_skus, days=d.n_days, dates=f"{d.date_start} to {d.date_end}",
        evaluation_window_from=d.test_from_date, answer_key=d.has_truth, injected_incidents=d.n_incidents, anomalous_rows=d.n_anomaly_rows, lp_flags=d.n_lp_flags,
        columns=[{"name": c.name, "label": c.label, "role": c.role} for c in d.columns if c.role not in ("feature", "context")],
        detection_features=[{"name": f, "label": pl.FEATURE_LABELS.get(f, f)} for f in d.detect_features],
        stats={k: v.model_dump() for k, v in (st.numeric.items() if st else [])},
        rows_by_category=st.rows_by_category if st else {}, units_sold=st.units_sold if st else None,
        net_stock_gap_units=st.net_variance_units if st else None, net_stock_gap_value_gbp=st.net_variance_value_gbp if st else None,
        import_mapping=d.detection.model_dump() if d.detection else None, warnings=d.warnings, source=_source(d),
    )


def _source(d: Any) -> dict[str, Any]:
    p = d.params or {}
    if d.kind == "connector":
        return {"type": "vendor connector", "connector_id": p.get("connector_id"), "connector": p.get("connector_name"), "vendor": p.get("vendor"), "window": f"{p.get('window_start')} to {p.get('synced_through')}", "synced_at": p.get("synced_at"), "answer_key": "demo vendor answer key" if d.has_truth else None}
    if d.kind == "upload":
        return {"type": "manual import", "file": p.get("source_file")}
    return {"type": "legacy synthetic dataset (made before connectors existed)"}


def preview_rows(dataset_id: str | None = None, table: str = "daily", rows: int = 5) -> dict[str, Any]:
    """Show the first rows of a dataset table.

    Args:
        dataset_id: Dataset id; defaults to the selected or most recent dataset.
        table: "daily" (store x SKU x day records), "stores", "skus" or "lp_flags" (past loss-prevention flags).
        rows: Number of rows (max 20).
    """
    d = _dataset(dataset_id)
    if d is None:
        return _err("No dataset yet.")
    from app.routers.datasets import preview

    try:
        pr = preview(d.id, table=table, rows=max(1, min(int(rows), 20)))
    except Exception as exc:  # noqa: BLE001
        return _err(str(getattr(exc, "detail", exc)))
    return _ok(dataset_id=d.id, table=table, total_rows=pr.total_rows, columns=pr.columns, rows=pr.rows)


# ---------------------------------------------------------------- models
def available_algorithms() -> dict[str, Any]:
    """The detection methods that can be trained, which engine each uses on this machine, and their settings."""
    return _ok(methods=[{
        "key": s.key, "label": s.label, "plain": pl.MODEL_PLAIN.get(s.key, s.plain_label), "available": s.available, "engine": s.engine, "reason": s.reason,
        "onnx_export": s.onnx_ok, "params": [{"name": p.name, "label": p.label, "default": p.default} for p in s.params],
    } for s in registry.all_specs()], recommended=config.RECOMMENDED_MODELS)


def list_models() -> dict[str, Any]:
    """List trained models (best average precision first) with plain metrics, which one is in use and the rule-of-thumb baseline."""
    ms = sorted(storage.list_models(), key=lambda m: -(m.metrics.average_precision or -1))[:ROW_CAP]
    base = next((m.metrics.average_precision for m in ms if m.key == "zscore"), None)
    return _ok(count=len(ms), baseline_average_precision=base, models=[{
        "model_id": m.model_id, "method": m.label, "key": m.key, "in_use": m.is_active, "dataset": m.dataset_name, "run": m.run_name,
        "average_precision": m.metrics.average_precision, "vs_baseline": round(m.metrics.average_precision / base, 2) if base and m.metrics.average_precision else None,
        "precision_at_1000": m.metrics.precision_at_k, "incident_recall": m.metrics.incident_recall, "value_captured_pct": m.metrics.value_captured_pct,
        "label_source": m.metrics.label_source, "engine": m.engine, "parent_model_id": m.parent_model_id, "created_at": m.created_at,
    } for m in ms])


def model_detail(model_id: str | None = None) -> dict[str, Any]:
    """Full detail of one model: metrics incl. detection rate by anomaly type, thresholds, top drivers, calibration, settings, export status.

    Args:
        model_id: Model id (m_...). Defaults to the model in use.
    """
    mid = model_id or storage.get_active_model_id()
    m = storage.get_model(mid) if mid else None
    if m is None:
        return _err("No model yet. Train one on the Train page (or propose a train job).")
    from app.services import model_export

    x = m.metrics
    return _ok(
        model_id=m.model_id, method=m.label, plain=pl.MODEL_PLAIN.get(m.key, ""), in_use=m.is_active, dataset=m.dataset_name, engine=m.engine, params=m.params,
        metrics={"average_precision": x.average_precision, "roc_auc": x.roc_auc, "precision_at_1000": x.precision_at_k, "recall_at_threshold": x.recall_at_threshold,
                 "precision_at_threshold": x.precision_at_threshold, "incident_recall": x.incident_recall, "value_captured_pct": x.value_captured_pct,
                 "lp_flag_recall": x.lp_recall, "label_source": x.label_source, "evaluation_rows": x.n_eval_rows, "fit_seconds": x.fit_seconds, "score_seconds_per_1m_rows": x.score_seconds_per_1m},
        incident_recall_by_type={pl.TYPE_LABEL.get(k, k): v for k, v in x.detection_by_type.items()},
        alert_rate=m.alert_rate, thresholds=m.thresholds.model_dump(),
        top_drivers=[{"feature": i.feature, "label": pl.FEATURE_LABELS.get(i.feature, i.feature), "share": i.importance} for i in m.importances[:8]],
        calibration={"source": m.calibration.source, "note": m.calibration.note}, notes=m.notes, feedback_evaluation=m.feedback_eval or None,
        onnx={"possible": m.onnx_ok, "reason": m.onnx_reason, "ready": model_export.onnx_status(m.model_id).ready},
    )


def list_experiments(limit: int = 5) -> dict[str, Any]:
    """Training runs (newest first) with their leaderboard and best model.

    Args:
        limit: Number of runs (max 10).
    """
    ex = training.experiments()[: max(1, min(int(limit), 10))]
    return _ok(runs=[{"job_id": e.job_id, "run_name": e.run_name, "dataset": e.dataset_name, "created_at": e.created_at, "status": e.status, "best_model_id": e.best_model_id,
                      "leaderboard": [{"model_id": m.model_id, "method": m.label, "average_precision": m.metrics.average_precision, "incident_recall": m.metrics.incident_recall} for m in e.models]} for e in ex])


# ---------------------------------------------------------------- detection runs and alerts
def list_detection_runs() -> dict[str, Any]:
    """Detection runs (newest first): which model produced each, alerts, value at risk, and whether that model is the one in use."""
    rs = storage.list_runs()[:ROW_CAP]
    return _ok(count=len(rs), runs=[r.model_dump() for r in rs])


def alert_summary(run_id: str | None = None) -> dict[str, Any]:
    """Summary of a detection run: alerts by severity and likely type, value at risk, stores affected, evaluation against the synthetic answer key, top stores and categories.

    Args:
        run_id: Detection run id (run_...). Defaults to the run selected in the app, else the newest run of the model in use.
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet. Run detection on the Act page (or propose a detect job).")
    try:
        rd = storage.load_run(rid)
    except LookupError as exc:
        return _err(str(exc))
    k = rd.run.kpis
    return _ok(
        **_run_note(rid), dataset=rd.run.dataset_name, rows_scored=k.rows_scored, alerts=k.incidents, flagged_days=k.flagged_rows, pct_days_flagged=k.pct_rows_flagged,
        value_at_risk_gbp=k.value_at_risk_gbp, stores_affected=k.stores_affected, by_severity=k.by_severity,
        by_likely_type={pl.TYPE_LABEL.get(t, t): n for t, n in k.by_type.items()},
        evaluation=rd.run.evaluation.model_dump() if rd.run.evaluation else None,
        top_stores=rd.aggregates.get("top_stores", [])[:5], top_categories=rd.aggregates.get("by_category", [])[:5], top_teams=rd.aggregates.get("top_teams", [])[:5],
        thresholds=rd.run.thresholds.model_dump(),
    )


def anomaly_trend(run_id: str | None = None, by: str = "severity", days: int = 28) -> dict[str, Any]:
    """Daily trend of flagged store-SKU-days in a run, split by severity or by likely type, plus £ at risk per day.

    Args:
        run_id: Detection run id; defaults to the selected/newest run.
        by: "severity" or "type".
        days: How many most recent days to return (max 90).
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet.")
    rd = storage.load_run(rid)
    tr = rd.aggregates.get("trend", [])[-max(1, min(int(days), 90)) :]
    if by == "type":
        rows = [{"date": t["date"], "value_gbp": t["value_gbp"], **{pl.TYPE_LABEL.get(k[5:], k[5:]): v for k, v in t.items() if k.startswith("type:")}} for t in tr]
    else:
        rows = [{"date": t["date"], "value_gbp": t["value_gbp"], "critical": t.get("critical", 0), "high": t.get("high", 0), "medium": t.get("medium", 0)} for t in tr]
    return _ok(**_run_note(rid), by=by, days=rows)


def hotspots(run_id: str | None = None, by: str = "store", top: int = 10) -> dict[str, Any]:
    """Where problems concentrate: top stores, SKUs, warehouse teams, categories or regions by £ at risk.

    Args:
        run_id: Detection run id; defaults to the selected/newest run.
        by: "store", "sku", "team", "category" or "region".
        top: How many (max 20).
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet.")
    rd = storage.load_run(rid)
    key = {"store": "top_stores", "sku": "top_skus", "team": "top_teams", "category": "by_category", "region": "by_region"}.get(by)
    if key is None:
        return _err("by must be store, sku, team, category or region.")
    return _ok(**_run_note(rid), by=by, hotspots=rd.aggregates.get(key, [])[: max(1, min(int(top), 20))])


def list_alerts(run_id: str | None = None, severity: str | None = None, likely_type: str | None = None, store_id: str | None = None, team: str | None = None, category: str | None = None, status: str | None = None, sort: str = "priority", limit: int = 10) -> dict[str, Any]:
    """List alerts (incidents) from a detection run with filters. Each alert has severity, likely type, value at risk, P(true anomaly), reasons and triage status.

    Args:
        run_id: Detection run id; defaults to the selected/newest run.
        severity: "critical", "high" or "medium" (comma-separated for several).
        likely_type: theft_external, theft_internal, scan_fraud, counting_error, receiving_error, data_entry_error, velocity_shift or unclear (comma-separated allowed).
        store_id: Store id such as S001.
        team: Warehouse team name.
        category: Category such as beauty.
        status: "open", "reviewed" or a triage outcome.
        sort: "priority" (default), "value", "p_true" or "recent".
        limit: Number of alerts (max 20).
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet.")
    split = lambda v: [x.strip() for x in v.split(",") if x.strip()] if v else None  # noqa: E731
    page = detection.list_alerts(rid, severity=split(severity), likely_type=split(likely_type), store_id=store_id, team=team, category=category, status=status, sort=sort, limit=max(1, min(int(limit), ROW_CAP)))
    return _ok(**_run_note(rid), total_matching=page.total, alerts=[{
        "alert_id": a.alert_id, "severity": a.severity, "store": f"{a.store_id} {a.store_name}", "sku": f"{a.sku_id} {a.sku_name}", "category": a.category,
        "team": a.warehouse_team, "dates": f"{a.start_date} to {a.end_date}" if a.n_days > 1 else a.start_date, "likely_type": pl.TYPE_LABEL.get(a.likely_type, a.likely_type),
        "value_at_risk_gbp": a.value_at_risk_gbp, "units_at_risk": a.units_at_risk, "p_true": a.p_true, "status": a.status, "top_reason": a.reasons[0] if a.reasons else None,
    } for a in page.alerts])


def explain_alert(alert_id: str, run_id: str | None = None) -> dict[str, Any]:
    """Why an alert was raised: reasons, likely type, score percentile, value at risk, P(true anomaly), triage status and the days around it.

    Args:
        alert_id: Alert id such as A000001.
        run_id: Detection run id; defaults to the selected/newest run.
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet.")
    try:
        a = detection.get_alert(rid, alert_id.strip().upper())
        s = detection.series(rid, a.store_id, a.sku_id)
    except LookupError as exc:
        return _err(str(exc))
    lo = str(np.datetime64(a.start_date) - np.timedelta64(4, "D"))
    hi = str(np.datetime64(a.end_date) + np.timedelta64(4, "D"))
    around = [p for p in s.points if lo <= p.date <= hi]
    return _ok(
        **_run_note(rid), alert_id=a.alert_id, severity=a.severity, store=f"{a.store_id} {a.store_name}", sku=f"{a.sku_id} {a.sku_name}", category=a.category, team=a.warehouse_team,
        dates=f"{a.start_date} to {a.end_date}", days=a.n_days, likely_type=pl.TYPE_LABEL.get(a.likely_type, a.likely_type), type_confidence=a.type_confidence,
        reasons=a.reasons, peak_percentile=a.peak_percentile, units_at_risk=a.units_at_risk, value_at_risk_gbp=a.value_at_risk_gbp, p_true=a.p_true, status=a.status,
        days_around=[{"date": p.date, "expected": p.expected_closing, "counted": p.counted_closing, "gap": p.variance_units, "sold": p.sold_units, "received": p.received_units, "voids": p.void_count, "after_hours": p.after_hours_scans, "percentile": p.percentile, "flagged": p.severity > 0} for p in around][:14],
        wording_rule="Describe the pattern as 'consistent with ...'; never accuse a person or team.",
    )


def sku_drilldown(store_id: str, sku_id: str, run_id: str | None = None) -> dict[str, Any]:
    """One SKU in one store over time: flagged days with reasons, alerts, loss-prevention flags and triage decisions, plus the last 14 days.

    Args:
        store_id: Store id such as S001.
        sku_id: SKU id such as K00001.
        run_id: Detection run id; defaults to the selected/newest run.
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet.")
    try:
        s = detection.series(rid, store_id.strip().upper(), sku_id.strip().upper())
    except LookupError as exc:
        return _err(str(exc))
    gaps = [p.variance_units for p in s.points]
    return _ok(
        **_run_note(rid),
        how_to_read="Expected stock is the book figure from yesterday's count plus today's movements; the daily count resets it, so a gap shows on the day it happens and does not carry forward. Say what the numbers show day by day; do not claim the book stayed wrong unless later days also show gaps.",
        store=f"{s.store_id} {s.store_name}", sku=f"{s.sku_id} {s.sku_name}", category=s.category, unit_cost=s.unit_cost, days=len(s.points),
        flagged_days=sum(p.severity > 0 for p in s.points), total_gap_units=int(sum(gaps)), alerts=[{"alert_id": a.alert_id, "dates": f"{a.start_date} to {a.end_date}", "severity": a.severity, "likely_type": pl.TYPE_LABEL.get(a.likely_type, a.likely_type), "value_at_risk_gbp": a.value_at_risk_gbp, "status": a.status} for a in s.alerts],
        reasons_by_day=dict(list(s.flagged_reasons.items())[:10]), lp_flags=[{"date": p.date, "flag": p.lp_flag} for p in s.points if p.lp_flag], triage=s.triage[:10],
        last_14_days=[{"date": p.date, "expected": p.expected_closing, "counted": p.counted_closing, "gap": p.variance_units, "sold": p.sold_units, "received": p.received_units, "promo": p.on_promo, "flagged": p.severity > 0} for p in s.points[-14:]],
    )


def search_series(q: str, run_id: str | None = None) -> dict[str, Any]:
    """Find store x SKU series by store id/name, SKU id/name or category words (e.g. "S012 mascara", "Leeds beauty").

    Args:
        q: Search words.
        run_id: Detection run id; defaults to the selected/newest run.
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet.")
    return _ok(matches=[m.model_dump() for m in detection.search(rid, q, limit=ROW_CAP)])


# ---------------------------------------------------------------- planner and triage
def investigation_plan(hours: float = 120, hourly_cost: float = 28, recovery_rate: float = 0.4, horizon_days: int = 28, run_id: str | None = None, team: str | None = None, severities: str | None = None) -> dict[str, Any]:
    """Plan investigator time: which open alerts to work, expected money recovered, cost, return on cost, breakeven hours, split by team, type and severity.

    Args:
        hours: Investigator hours available.
        hourly_cost: Cost of one investigator hour in GBP.
        recovery_rate: Share of the money at risk recovered when a real problem is investigated (0-1).
        horizon_days: Days of continuing loss that acting now prevents.
        run_id: Detection run id; defaults to the selected/newest run.
        team: Limit to one warehouse team.
        severities: Comma-separated severities to include (default all).
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet.")
    sev = [s.strip() for s in severities.split(",")] if severities else None
    try:
        p = planner.plan(PlanRequest(run_id=rid, hours=float(hours), hourly_cost=float(hourly_cost), recovery_rate=float(recovery_rate), horizon_days=int(horizon_days), teams=[team] if team else None, severities=sev))  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))
    q = f"hours={hours}&hourly_cost={hourly_cost}&recovery_rate={recovery_rate}&horizon_days={horizon_days}"
    return _ok(
        **_run_note(rid), hours=p.hours, alerts_selected=p.n_selected, open_alerts=p.n_candidates, hours_used=p.hours_used, cost_gbp=p.cost, expected_recovered_gbp=p.expected_recovered,
        net_benefit_gbp=p.net_benefit, return_on_cost=p.roi, breakeven_hours=p.breakeven_hours, naive_order_expected_gbp=p.naive_expected, calibration_source=p.calibration_source,
        by_team=[b.model_dump() for b in p.by_team[:8]], by_type=[{**b.model_dump(), "key": pl.TYPE_LABEL.get(b.key, b.key)} for b in p.by_type], by_severity=[b.model_dump() for b in p.by_severity],
        first_10=[r.model_dump(include={"priority", "alert_id", "team", "store_name", "sku_name", "likely_type", "severity", "p_true", "expected_value_gbp", "minutes"}) for r in p.top_rows[:10]],
        worklist_csv=f"/api/plan/{rid}/worklist.csv?{q}", worklist_zip=f"/api/plan/{rid}/worklist.zip?{q}",
        caveat="Estimates: they depend on the recovery rate and on P(true anomaly).",
    )


def compare_plans(hours_list: list[float], hourly_cost: float = 28, recovery_rate: float = 0.4, horizon_days: int = 28, run_id: str | None = None) -> dict[str, Any]:
    """Compare several investigator-hour budgets side by side (alerts covered, expected recovery, cost, return on cost).

    Args:
        hours_list: Hours to compare, e.g. [40, 120, 300].
        hourly_cost: Cost of one investigator hour in GBP.
        recovery_rate: Share of the money at risk recovered when a real problem is investigated.
        horizon_days: Days of continuing loss that acting now prevents.
        run_id: Detection run id; defaults to the selected/newest run.
    """
    rid = _run_id(run_id)
    if not rid:
        return _err("No detection run yet.")
    rows = []
    for h in list(hours_list)[:6]:
        p = planner.plan(PlanRequest(run_id=rid, hours=float(h), hourly_cost=float(hourly_cost), recovery_rate=float(recovery_rate), horizon_days=int(horizon_days)))
        rows.append({"hours": p.hours, "alerts": p.n_selected, "expected_recovered_gbp": p.expected_recovered, "cost_gbp": p.cost, "return_on_cost": p.roi, "net_benefit_gbp": p.net_benefit})
    return _ok(**_run_note(rid), plans=rows, caveat="Estimates: they depend on the recovery rate and on P(true anomaly).")


def triage_summary(dataset_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    """What teams decided about alerts: reviewed count, precision overall and by day, type, severity and team, and whether retraining with feedback is possible.

    Args:
        dataset_id: Dataset id; defaults to the dataset of the selected/newest run.
        run_id: Detection run id; defaults to the selected/newest run.
    """
    rid = _run_id(run_id)
    if not dataset_id:
        if rid:
            dataset_id = storage.load_run(rid).run.dataset_id
        else:
            d = _dataset(None)
            dataset_id = d.id if d else None
    if not dataset_id:
        return _err("No dataset yet.")
    s = triage.summary(dataset_id, rid)
    return _ok(**_jsonable(s.model_dump()))


# ---------------------------------------------------------------- jobs, knowledge, state
def propose_job(kind: str, params: dict[str, Any] | None = None, session_id: str = "mcp") -> dict[str, Any]:
    """Propose an action for the user to confirm; nothing runs until they press Confirm.

    Args:
        kind: One of
            "sync" (connector_id, full: true/false) - pull new days from a vendor and build a fresh snapshot;
            "train" (dataset_id, models: list of zscore/iforest/autoencoder/lof/ensemble, quick: true/false, alert_rate); "detect" (dataset_id, model_id);
            "retrain_feedback" (model_id, alpha); "activate_model" (model_id); "configure" (dataset_id, column_map) for imported CSVs;
            "export_dataset" (dataset_id); "export_onnx" (model_id);
            "create_schedule" (name, connector_id, at "HH:MM", days ["mon",...] or every_hours, timezone, model_policy active/fixed/retrain,
            model_id, models [algorithm keys -> retrain], activate_retrained, auto_tasks true/false, severities, min_value_gbp, max_tasks);
            "update_schedule" (schedule_id plus any create_schedule field); "run_schedule" (schedule_id);
            "vendor_task" (run_id, tasks: [{alert_id, type?, priority?, note?, sop_id?, sop_step?}]) - raise tasks in the vendor's system.
        params: Parameters for that kind; omitted ones get sensible defaults (latest dataset, model in use, the only connector, all four methods).
        session_id: Conversation id (filled in automatically in the app).
    """
    try:
        p = proposals.create(session_id, kind, params or {})
    except proposals.ProposalError as exc:
        return _err(str(exc))
    return {"status": "proposed", "proposal": p.model_dump(include={"proposal_id", "kind", "title", "summary", "estimate_seconds", "warnings", "params", "status"})}


def job_status(job_id: str | None = None) -> dict[str, Any]:
    """Status of background jobs: one job by id, or everything running plus the last few finished.

    Args:
        job_id: Job id (job_...); omit for the current list.
    """
    def row(j: Any) -> dict[str, Any]:
        return {"job_id": j.job_id, "type": j.type, "title": j.title, "status": j.status, "percent": round(j.percent), "step": j.step, "eta_seconds": j.eta_seconds, "elapsed_seconds": j.elapsed_seconds, "queue_position": j.queue_position, "error": j.error, "result": j.result, "warnings": j.warnings}

    if job_id:
        j = jobs.get(job_id)
        if j is None:
            return _err(f"Job '{job_id}' not found (jobs live in memory until the server restarts).")
        return _ok(jobs=[row(j)])
    active = jobs.list_jobs(active_only=True, limit=10)
    recent = [j for j in jobs.list_jobs(limit=8) if j.status not in ("queued", "running")][:5]
    return _ok(jobs=[row(j) for j in active + recent], n_active=len(active))


def search_docs(query: str, k: int = 4) -> dict[str, Any]:
    """Search the app's documentation (user guide, README, the leadership story, glossary) for how-to and why questions.

    Args:
        query: Free-text question or keywords.
        k: Number of passages (max 8).
    """
    hits = knowledge.search(query, k=max(1, min(int(k), 8)))
    return _ok(hits=hits, count=len(hits))


def explain_metric(term: str) -> dict[str, Any]:
    """Explain a metric, concept or field in plain language (e.g. "average precision", "shrinkage", "sweethearting", "void_z", "P(true)").

    Args:
        term: The term to explain.
    """
    e = pl.explain(term)
    out: dict[str, Any] = {}
    if e:
        out = {"term": e.term, "plain": e.plain, "detail": e.detail}
    key = (term or "").strip().lower()
    if key in pl.FEATURE_LABELS:
        out["field"] = {"name": key, "label": pl.FEATURE_LABELS[key]}
    if key in pl.MODEL_PLAIN:
        out["method"] = {"key": key, "plain": pl.MODEL_PLAIN[key]}
    if not out:
        return _err(f"No glossary entry for '{term}'. Try search_docs.")
    return _ok(**out)


def app_state(page: str = "overview", selected_dataset_id: str | None = None, selected_run_id: str | None = None, active_model_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    """What the app currently holds and what the user is looking at: datasets, models, model in use, detection runs, triage, jobs, proposals.

    Args:
        page: The page the user is on (filled in automatically in the app).
        selected_dataset_id: Selected dataset (automatic in the app).
        selected_run_id: Selected detection run (automatic in the app).
        active_model_id: Model in use (automatic in the app).
        session_id: Conversation id (automatic in the app).
    """
    ui = UiState(page=page, selected_dataset_id=selected_dataset_id, selected_run_id=selected_run_id, active_model_id=active_model_id)
    return _ok(**_jsonable(build_context_pack(ui, session_id)))


def usage_summary(session_id: str | None = None) -> dict[str, Any]:
    """The assistant's own team and running costs: which agents exist, what each does, and per-agent invocations, model calls, tool calls, tokens and cost in USD.

    Args:
        session_id: Limit to one conversation; omit for all-time totals.
    """
    from app.assistant import usage

    rep = usage.full_report(session_id)
    agents = [{k: a[k] for k in ("name", "label", "description", "n_tools", "invocations", "llm_calls", "tool_calls", "prompt_tokens", "completion_tokens", "cost_usd")} for a in rep["agents"]]
    return _ok(scope="this conversation" if session_id else "all time", since=rep["since"], model=rep["model"], pricing=rep["pricing"], totals=rep["totals"], agents=agents, top_tools=rep["tools"][:8],
               note="Costs are estimates from token counts and the price list named in 'pricing'; 'unpriced_calls' had no known price.")


# ---------------------------------------------------------------- vendor connectors, schedules, vendor tasks, SOPs
def _conn_row(c: Any) -> dict[str, Any]:
    caps = c.capabilities or {}
    last = c.last_sync
    return {
        "connector_id": c.id, "name": c.name, "vendor": (caps.get("vendor") or {}).get("name"), "enabled": c.enabled, "url": c.url,
        "vendor_status": caps.get("status"), "vendor_data_through": (caps.get("data_range") or {}).get("last_date"),
        "last_sync": {"at": last.at, "status": last.status, "synced_through": last.synced_through, "rows": last.rows, "error": last.error, "warnings": last.warnings[:3]} if last else None,
        "window_days": c.window_days, "snapshots_kept": c.retention, "answer_key": "demo vendor only" if (caps.get("features") or {}).get("answer_key") else "none",
        "task_types": caps.get("task_types") or [], "open_vendor_tasks": vendor_tasks.open_count(c.id), "backoffice_url": caps.get("backoffice_url"),
    }


def list_connectors() -> dict[str, Any]:
    """The vendor systems Sentinel reads inventory from over MCP (and can send approved tasks to): status, last sync, data range and open tasks. Tokens are never shown."""
    items = connectors.list_all()
    if not items:
        return _ok(count=0, connectors=[], hint="No vendor connector yet. Add one on the Data page (MCP URL + token).")
    return _ok(count=len(items), connectors=[_conn_row(c) for c in items])


def connector_status(connector_id: str | None = None, test: bool = False) -> dict[str, Any]:
    """Health of one vendor connector: last sync result and warnings (e.g. a stale feed), its snapshots, and optionally a live connection test.

    Args:
        connector_id: Connector id (conn_...); defaults to the only connector.
        test: Also call the vendor now to check it answers (takes a second).
    """
    try:
        c = connectors.get(connector_id)
    except LookupError as exc:
        return _err(str(exc))
    out = _conn_row(c)
    out["snapshots"] = [{"dataset_id": d.id, "dates": f"{d.date_start} to {d.date_end}", "rows": d.n_rows, "created_at": d.created_at} for d in sorted(connectors.connector_datasets(c.id), key=lambda d: d.created_at, reverse=True)]
    if test:
        t = connectors.test(c)
        out["test"] = {"ok": t.ok, "error": t.error, "seconds": t.seconds}
    if c.last_sync and c.last_sync.status == "failed":
        out["sop"] = "data-feed-failure"
    return _ok(**_jsonable(out))


def vendor_lookup(store_id: str, sku_id: str, connector_id: str | None = None, days: int = 7) -> dict[str, Any]:
    """LIVE stock position of one SKU in one store, read from the vendor's system right now (not from a snapshot): on-hand count and recent movements.

    Args:
        store_id: Store id, e.g. "S003" (defaults to the store open in the drill-down).
        sku_id: SKU id, e.g. "K00012" (defaults to the SKU open in the drill-down).
        connector_id: Connector id; defaults to the only connector.
        days: Days of movements to show (max 14).
    """
    try:
        pos = connectors.stock_position(connector_id, store_id, sku_id, max(1, min(int(days), 14)))
    except (LookupError, connectors.ConnectorError) as exc:
        return _err(str(exc))
    return _ok(live=True, note=f"Live from the vendor system, as of business date {pos.get('as_of')}.", **_jsonable(pos))


def list_vendor_tasks(connector_id: str | None = None, status: str | None = None, store_id: str | None = None, alert_id: str | None = None, run_id: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Tasks Sentinel raised in vendor systems (recounts, investigations, audits) and their status and outcome as last read back.

    Args:
        connector_id: Limit to one connector.
        status: "open" (not yet done or rejected), "done", "rejected", "acknowledged" or "in_progress".
        store_id: Limit to one store.
        alert_id: Tasks for one alert (needs run_id, or the run selected in the app).
        run_id: Detection run of that alert.
        limit: Max rows (max 20).
    """
    key = None
    if alert_id:
        rid = _run_id(run_id)
        if not rid:
            return _err("Name the run the alert belongs to.")
        try:
            key = detection.get_alert(rid, alert_id).alert_key
        except LookupError as exc:
            return _err(str(exc))
    items = vendor_tasks.list_tasks(connector_id=connector_id, status=status, store_id=store_id, alert_key=key, limit=max(1, min(int(limit), ROW_CAP)))
    return _ok(count=len(items), tasks=[t.model_dump(exclude={"alert", "feedback_recorded"}) for t in items])


def list_schedules() -> dict[str, Any]:
    """Scheduled pipelines (sync a vendor, pick or retrain a model, detect, propose vendor tasks): when each runs next and how its last run went."""
    items = scheduler.list_all()
    st = scheduler.status()
    pending = proposals.list_pending(source="scheduler")
    return _ok(engine_running=st.running, count=len(items), schedules=[{
        "schedule_id": s.id, "name": s.name, "enabled": s.enabled, "description": scheduler.describe(s), "next_run_at_utc": s.next_run_at,
        "model_policy": s.pipeline.model_policy, "model_id": s.pipeline.model_id, "algorithms": [m.key for m in s.pipeline.train.models] if s.pipeline.model_policy == "retrain" else None,
        "auto_tasks": s.pipeline.auto_tasks.model_dump() if s.pipeline.auto_tasks.enabled else False, "last_run": s.last_run,
    } for s in items], approvals_waiting=[{"proposal_id": p.proposal_id, "title": p.title, "created_at": p.created_at} for p in pending[:5]])


def schedule_history(schedule_id: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Recent scheduled runs: status, new alerts found, model used, errors (with the SOP to follow when a run failed).

    Args:
        schedule_id: Limit to one schedule (sch_...).
        limit: Max runs (max 20).
    """
    runs = scheduler.list_runs(schedule_id, limit=max(1, min(int(limit), ROW_CAP)))
    return _ok(count=len(runs), runs=[r.model_dump() for r in runs])


def get_sop(sop_id: str | None = None, alert_id: str | None = None, run_id: str | None = None, likely_type: str | None = None) -> dict[str, Any]:
    """The standard operating procedure to follow: for an alert (with its escalation level, filled-in steps and tasks already raised), for an alert type, or by SOP id.

    Args:
        sop_id: SOP id, e.g. "missing-inventory-response", "theft-external", "data-feed-failure", "false-positive-handling".
        alert_id: An alert (A000123); uses run_id or the run selected in the app.
        run_id: Detection run of the alert.
        likely_type: An alert type (theft_external, theft_internal, scan_fraud, counting_error, receiving_error, data_entry_error, velocity_shift, unclear).
    """
    try:
        if alert_id:
            rid = _run_id(run_id)
            if not rid:
                return _err("Name the run the alert belongs to.")
            a = sops.for_alert(rid, alert_id)
            return _ok(
                alert={"alert_id": a.alert.alert_id, "store": a.alert.store_name, "sku": a.alert.sku_name, "severity": a.alert.severity, "value_at_risk_gbp": a.alert.value_at_risk_gbp, "likely_type": a.alert.likely_type},
                sop={"id": a.sop.id, "title": a.sop.title, "version": a.sop.version, "owner_role": a.sop.owner_role},
                escalation=a.escalation.model_dump() if a.escalation else None,
                steps=[{"id": s.id, "text": s.text, "role": s.role, "due_hours": s.due_hours, "evidence": s.evidence, "vendor_task": (s.vendor_task or {}).get("type"), "already_raised": [f"{t.task_id} ({t.status})" for t in s.raised]} for s in a.steps],
                closure=a.sop.closure, can_raise_vendor_tasks=a.can_raise_tasks,
                hint="Offer to raise the step's vendor task with propose_job(kind='vendor_task') if the user wants; never raise one without confirmation.",
            )
        sid = sop_id or sops.sop_id_for_type(likely_type)
        if not sid:
            return _ok(sops=[x.model_dump() for x in sops.list_sops()], hint="Pick one by id.")
        sop = sops.get(sid)
        return _ok(sop={"id": sop.id, "title": sop.title, "version": sop.version, "summary": sop.summary, "owner_role": sop.owner_role, "applies_to": sop.applies_to},
                   steps=[{"id": s.id, "text": s.text, "role": s.role, "due_hours": s.due_hours, "vendor_task": (s.vendor_task or {}).get("type")} for s in sop.steps],
                   escalation=sop.escalation or None, closure=sop.closure, body=sop.body[: config.ASSISTANT_TEXT_CAP * 3])
    except LookupError as exc:
        return _err(str(exc))


def find_sop(query: str, k: int = 3) -> dict[str, Any]:
    """Search the SOPs (what to do if stock is missing, escalation, CCTV, refunds, recounts, failed syncs, false alarms) by keywords.

    Args:
        query: Free-text question, e.g. "who do I tell if a critical alert is over 500 pounds".
        k: Number of passages (max 6).
    """
    hits = [h for h in knowledge.search(query, k=12) if str(h.get("source", "")).startswith("SOP")][: max(1, min(int(k), 6))]
    return _ok(hits=hits, count=len(hits), sops=[x.id for x in sops.list_sops()])


CATALOGUE = [
    list_datasets, describe_dataset, preview_rows, available_algorithms, list_models, model_detail, list_experiments,
    list_detection_runs, alert_summary, anomaly_trend, hotspots, list_alerts, explain_alert, sku_drilldown, search_series,
    investigation_plan, compare_plans, triage_summary, propose_job, job_status, search_docs, explain_metric, app_state, usage_summary,
    list_connectors, connector_status, vendor_lookup, list_vendor_tasks, list_schedules, schedule_history, get_sop, find_sop,
]
