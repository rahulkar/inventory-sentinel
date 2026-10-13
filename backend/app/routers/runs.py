"""Detection runs, alerts, dashboard and the store x SKU drill-down."""
from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import Alert, AlertPage, DetectionRun, DetectionRunSummary, DetectRequest, ExecutiveSummary, Job, SeriesMatch, SeriesResponse
from app.services import detection, executive, reclassify, storage

router = APIRouter(prefix="/api", tags=["detection"])


def _load(run_id: str) -> storage.RunData:
    try:
        return storage.load_run(run_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/detect", response_model=Job, status_code=202)
def detect(req: DetectRequest) -> Job:
    try:
        return detection.start_job(req)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/runs", response_model=list[DetectionRunSummary])
def runs(dataset_id: str | None = None) -> list[DetectionRunSummary]:
    return storage.list_runs(dataset_id)


@router.get("/runs/{run_id}", response_model=DetectionRun)
def run(run_id: str) -> DetectionRun:
    return _load(run_id).run


@router.delete("/runs/{run_id}")
def delete_run(run_id: str) -> dict[str, bool]:
    if not storage.delete_run(run_id):
        raise HTTPException(404, "Run not found.")
    return {"deleted": True}


@router.get("/runs/{run_id}/dashboard")
def dashboard(run_id: str) -> dict:
    rd = _load(run_id)
    return {"run": rd.run.model_dump(), **rd.aggregates}


@router.get("/runs/{run_id}/executive", response_model=ExecutiveSummary)
def executive_summary(run_id: str, days: int = 90, region: str | None = None, store_id: str | None = None, category: str | None = None) -> ExecutiveSummary:
    _load(run_id)
    return executive.summary(run_id, days=max(0, days), region=region or None, store_id=store_id or None, category=category or None)


@router.post("/runs/{run_id}/reclassify")
async def reclassify_unclear(run_id: str, days: int = 90, region: str | None = None, store_id: str | None = None, category: str | None = None, redo: bool = False) -> dict:
    """AI assist: suggest a cause for the open unclear cases in this view (highest revenue at risk first)."""
    _load(run_id)
    keys = executive.open_keys(run_id, days=max(0, days), region=region or None, store_id=store_id or None, category=category or None)
    try:
        return await reclassify.run(run_id, keys, redo=redo)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/runs/{run_id}/alerts", response_model=AlertPage)
def alerts(
    run_id: str,
    severity: list[str] | None = Query(None),
    likely_type: list[str] | None = Query(None),
    store_id: str | None = None,
    team: str | None = None,
    category: str | None = None,
    status: str | None = None,
    q: str | None = None,
    sort: str = "priority",
    limit: int = 50,
    offset: int = 0,
    answer_key: bool = False,
) -> AlertPage:
    _load(run_id)
    return detection.list_alerts(run_id, severity=severity, likely_type=likely_type, store_id=store_id, team=team, category=category, status=status, q=q, sort=sort, limit=max(1, min(limit, 500)), offset=max(0, offset), answer_key=answer_key)


@router.get("/runs/{run_id}/alerts.csv")
def alerts_csv(run_id: str) -> StreamingResponse:
    rd = _load(run_id)
    df = rd.incidents.drop(columns=[c for c in ("truth_type", "peak_row", "store_code", "sku_code", "start_day") if c in rd.incidents])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="alerts_{run_id}.csv"'})


@router.get("/runs/{run_id}/alerts/{alert_id}", response_model=Alert)
def alert(run_id: str, alert_id: str, answer_key: bool = False) -> Alert:
    _load(run_id)
    try:
        return detection.get_alert(run_id, alert_id, answer_key)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/runs/{run_id}/series", response_model=SeriesResponse)
def series(run_id: str, store_id: str, sku_id: str, answer_key: bool = False) -> SeriesResponse:
    _load(run_id)
    try:
        return detection.series(run_id, store_id, sku_id, answer_key)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/runs/{run_id}/search", response_model=list[SeriesMatch])
def search(run_id: str, q: str = "", limit: int = 20) -> list[SeriesMatch]:
    _load(run_id)
    return detection.search(run_id, q, limit=max(1, min(limit, 50)))


@router.post("/runs/{run_id}/recalibrate")
def recalibrate(run_id: str) -> dict:
    _load(run_id)
    try:
        return detection.recalibrate(run_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
