"""Adapters that expose the tool catalogue to Google ADK (async, with UI state injected from the session).

When a tool's run_id / dataset_id / alert_id argument is left empty, the wrapper fills it from what the user has selected
in the app (session state keys "ui:*"), so "why was this flagged?" works on the alert that is open on screen.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable

from google.adk.tools import ToolContext

from app.assistant import tools as T

UI_KEYS = ("ui:page", "ui:tab", "ui:selected_dataset_id", "ui:selected_run_id", "ui:selected_alert_id", "ui:drill_store_id", "ui:drill_sku_id", "ui:active_model_id", "ui:session_id", "ui:selected_schedule_id")
FROM_UI = {"run_id": "selected_run_id", "dataset_id": "selected_dataset_id", "alert_id": "selected_alert_id", "store_id": "drill_store_id", "sku_id": "drill_sku_id"}


def _ui(tool_context: ToolContext | None) -> dict[str, Any]:
    if tool_context is None:
        return {}
    st = tool_context.state
    return {k.split(":", 1)[1]: st.get(k) for k in UI_KEYS}


def as_async_tool(fn: Callable[..., dict[str, Any]]) -> Callable[..., Any]:
    """Run a sync catalogue function in a worker thread; fill empty ids from the UI; keep the signature and docstring."""
    sig = inspect.signature(fn)
    fills = [p for p in sig.parameters if p in FROM_UI]

    @functools.wraps(fn)
    async def wrapper(**kwargs: Any) -> dict[str, Any]:
        ctx = kwargs.pop("tool_context", None)
        if fills:
            ui = _ui(ctx)
            for p in fills:
                if not kwargs.get(p) and ui.get(FROM_UI[p]):
                    kwargs[p] = ui[FROM_UI[p]]
        try:
            return await asyncio.to_thread(fn, **kwargs)
        except LookupError as exc:  # e.g. a run id filled from the UI that has since been deleted: tell the model, don't end the turn
            return T._err(str(exc))

    params = list(sig.parameters.values())
    if fills:
        params.append(inspect.Parameter("tool_context", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=ToolContext))
    wrapper.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]
    del wrapper.__wrapped__  # ADK should inspect our signature, not the original's
    return wrapper


async def propose_job(kind: str, params: dict[str, Any] | None = None, tool_context: ToolContext = None) -> dict[str, Any]:  # type: ignore[assignment]
    """Propose an action for the user to confirm; nothing runs until they press Confirm in the chat.

    Args:
        kind: One of
            "sync" (connector_id, full) - pull new days from a vendor connector into a fresh snapshot;
            "train" (dataset_id, models: list of method keys zscore/iforest/autoencoder/lof/ensemble, quick: true/false, alert_rate); "detect" (dataset_id, model_id);
            "retrain_feedback" (model_id, alpha); "activate_model" (model_id); "configure" (dataset_id, column_map) for imported CSVs;
            "export_dataset" (dataset_id); "export_onnx" (model_id);
            "create_schedule" (name, connector_id, at "HH:MM", days ["mon",...] or every_hours, timezone, model_policy "active"/"fixed"/"retrain",
            model_id, models [algorithm keys, implies retrain], activate_retrained, auto_tasks true/false, severities, min_value_gbp, max_tasks);
            "update_schedule" (schedule_id + any create_schedule field); "run_schedule" (schedule_id);
            "vendor_task" (run_id, tasks: [{alert_id, type?, priority?, note?, sop_id?, sop_step?}]) - raise tasks in the vendor's system.
        params: Parameters for that kind; omitted ones get sensible defaults (the selected dataset or run, the model in use, the only connector).
    """
    ui = _ui(tool_context)
    p = dict(params or {})
    if kind in ("train", "detect", "export_dataset", "configure") and not p.get("dataset_id") and ui.get("selected_dataset_id"):
        p["dataset_id"] = ui["selected_dataset_id"]
    if kind == "vendor_task":
        if not p.get("run_id") and ui.get("selected_run_id"):
            p["run_id"] = ui["selected_run_id"]
        if not p.get("tasks") and not p.get("alert_id") and ui.get("selected_alert_id"):
            p["tasks"] = [{"alert_id": ui["selected_alert_id"]}]
    if kind in ("update_schedule", "run_schedule") and not p.get("schedule_id") and ui.get("selected_schedule_id"):
        p["schedule_id"] = ui["selected_schedule_id"]
    return await asyncio.to_thread(T.propose_job, kind, p, ui.get("session_id") or "chat")


async def app_state(tool_context: ToolContext = None) -> dict[str, Any]:  # type: ignore[assignment]
    """What the app currently holds and what the user is looking at: datasets, models, model in use, detection runs, triage, jobs, proposals."""
    ui = _ui(tool_context)
    return await asyncio.to_thread(T.app_state, ui.get("page") or "overview", ui.get("selected_dataset_id"), ui.get("selected_run_id"), ui.get("active_model_id"), ui.get("session_id"))


async def usage_summary(all_time: bool = True, tool_context: ToolContext = None) -> dict[str, Any]:  # type: ignore[assignment]
    """The assistant's own team and running costs: which agents exist, what each does, and per-agent invocations, model calls, tool calls, tokens and cost in USD.

    Args:
        all_time: True for totals since the counters were last reset; False for this conversation only.
    """
    ui = _ui(tool_context)
    return await asyncio.to_thread(T.usage_summary, None if all_time else ui.get("session_id"))


list_datasets = as_async_tool(T.list_datasets)
describe_dataset = as_async_tool(T.describe_dataset)
preview_rows = as_async_tool(T.preview_rows)
available_algorithms = as_async_tool(T.available_algorithms)
list_models = as_async_tool(T.list_models)
model_detail = as_async_tool(T.model_detail)
list_experiments = as_async_tool(T.list_experiments)
list_detection_runs = as_async_tool(T.list_detection_runs)
alert_summary = as_async_tool(T.alert_summary)
anomaly_trend = as_async_tool(T.anomaly_trend)
hotspots = as_async_tool(T.hotspots)
list_alerts = as_async_tool(T.list_alerts)
explain_alert = as_async_tool(T.explain_alert)
sku_drilldown = as_async_tool(T.sku_drilldown)
search_series = as_async_tool(T.search_series)
investigation_plan = as_async_tool(T.investigation_plan)
compare_plans = as_async_tool(T.compare_plans)
triage_summary = as_async_tool(T.triage_summary)
job_status = as_async_tool(T.job_status)
search_docs = as_async_tool(T.search_docs)
explain_metric = as_async_tool(T.explain_metric)
list_connectors = as_async_tool(T.list_connectors)
connector_status = as_async_tool(T.connector_status)
vendor_lookup = as_async_tool(T.vendor_lookup)
list_vendor_tasks = as_async_tool(T.list_vendor_tasks)
list_schedules = as_async_tool(T.list_schedules)
schedule_history = as_async_tool(T.schedule_history)
get_sop = as_async_tool(T.get_sop)
find_sop = as_async_tool(T.find_sop)

COMMON = [app_state, search_docs, explain_metric, job_status, usage_summary]
DATA = [list_datasets, describe_dataset, preview_rows]
VENDOR = [list_connectors, connector_status, vendor_lookup, list_vendor_tasks]
OPS = [list_schedules, schedule_history]
SOP = [get_sop, find_sop]
MODEL = [list_models, model_detail, list_experiments, available_algorithms, triage_summary]
ALERTS = [list_detection_runs, alert_summary, anomaly_trend, hotspots, list_alerts, explain_alert, sku_drilldown, search_series]
PLAN = [list_detection_runs, alert_summary, investigation_plan, compare_plans, hotspots]
JOBS = [propose_job]


def unique(*groups: list[Callable[..., Any]]) -> list[Callable[..., Any]]:
    seen: set[str] = set()
    out: list[Callable[..., Any]] = []
    for g in groups:
        for fn in g:
            if fn.__name__ not in seen:
                seen.add(fn.__name__)
                out.append(fn)
    return out


def tool_label(name: str, args: dict[str, Any]) -> str:
    """Human-readable labels for the activity chips and the thinking trail in the chat UI."""
    a = args or {}
    labels = {
        "list_datasets": "Listing datasets",
        "describe_dataset": f"Describing dataset {a.get('dataset_id') or '(selected)'}",
        "preview_rows": f"Previewing {a.get('table', 'daily')} rows",
        "available_algorithms": "Checking available methods",
        "list_models": "Listing trained models",
        "model_detail": f"Reading model {a.get('model_id') or 'in use'}",
        "list_experiments": "Listing training runs",
        "list_detection_runs": "Listing detection runs",
        "alert_summary": "Summarising the detection run",
        "anomaly_trend": f"Reading the anomaly trend by {a.get('by', 'severity')}",
        "hotspots": f"Finding hotspots by {a.get('by', 'store')}",
        "list_alerts": "Listing alerts" + (f" ({a.get('severity')})" if a.get("severity") else ""),
        "explain_alert": f"Explaining alert {a.get('alert_id') or '(open)'}",
        "sku_drilldown": f"Drilling into {a.get('store_id') or ''} {a.get('sku_id') or ''}".strip(),
        "search_series": f"Searching for '{a.get('q', '')}'",
        "investigation_plan": f"Planning {a.get('hours', 120)} investigator hours",
        "compare_plans": f"Comparing {len(a.get('hours_list') or [])} hour budgets",
        "triage_summary": "Reading team feedback",
        "propose_job": f"Proposing a {a.get('kind', '')} job",
        "job_status": "Checking jobs",
        "search_docs": f"Searching the guide for '{a.get('query', '')}'",
        "explain_metric": f"Looking up '{a.get('term', '')}'",
        "app_state": "Reading what is loaded",
        "usage_summary": "Reading the team's usage and cost",
        "list_connectors": "Listing vendor connectors",
        "connector_status": "Checking the vendor connector" + (" (live test)" if a.get("test") else ""),
        "vendor_lookup": f"Asking the vendor for {a.get('store_id') or ''} {a.get('sku_id') or ''} stock".replace("  ", " "),
        "list_vendor_tasks": "Reading vendor tasks",
        "list_schedules": "Listing schedules",
        "schedule_history": "Reading scheduled runs",
        "get_sop": "Opening the SOP" + (f" for {a.get('alert_id')}" if a.get("alert_id") else f" {a.get('sop_id')}" if a.get("sop_id") else ""),
        "find_sop": f"Searching SOPs for '{a.get('query', '')}'",
    }
    return labels.get(name, name.replace("_", " "))
