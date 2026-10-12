"""Investigation planner and triage endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.schemas import InvestigationPlan, PlanRequest, SimulateTriageRequest, TriageBulk, TriageDecision, TriageSummary
from app.services import planner, storage, triage

router = APIRouter(prefix="/api", tags=["planner"])


def _req(run_id: str, hours: float, hourly_cost: float, recovery_rate: float, horizon_days: int, severities: list[str] | None, teams: list[str] | None) -> PlanRequest:
    return PlanRequest(run_id=run_id, hours=hours, hourly_cost=hourly_cost, recovery_rate=recovery_rate, horizon_days=horizon_days, severities=severities or None, teams=teams or None)  # type: ignore[arg-type]


@router.post("/plan", response_model=InvestigationPlan)
def plan(req: PlanRequest) -> InvestigationPlan:
    try:
        return planner.plan(req)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/plan/{run_id}/worklist.csv")
def worklist_csv(run_id: str, hours: float = 120, hourly_cost: float = 28, recovery_rate: float = 0.4, horizon_days: int = 28, team: str | None = None, severities: list[str] | None = Query(None), teams: list[str] | None = Query(None)) -> StreamingResponse:
    try:
        text = planner.worklist_csv(_req(run_id, hours, hourly_cost, recovery_rate, horizon_days, severities, teams), team)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    name = f"worklist_{storage.safe_name(team) if team else 'all'}_{run_id}.csv"
    return StreamingResponse(iter([text]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/plan/{run_id}/worklist.zip")
def worklist_zip(run_id: str, hours: float = 120, hourly_cost: float = 28, recovery_rate: float = 0.4, horizon_days: int = 28, severities: list[str] | None = Query(None), teams: list[str] | None = Query(None)) -> Response:
    try:
        data = planner.worklist_zip(_req(run_id, hours, hourly_cost, recovery_rate, horizon_days, severities, teams))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="worklists_{run_id}.zip"'})


# ---------------------------------------------------------------- triage
@router.post("/triage")
def decide(req: TriageDecision) -> dict:
    try:
        return {"saved": triage.decide(req.run_id, [req.alert_id], req.outcome, req.note)}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/triage/bulk")
def decide_bulk(req: TriageBulk) -> dict:
    try:
        return {"saved": triage.decide(req.run_id, req.alert_ids, req.outcome, req.note)}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/triage")
def decisions(dataset_id: str) -> list[dict]:
    return list(triage.latest(dataset_id).values())


@router.get("/triage/summary", response_model=TriageSummary)
def summary(dataset_id: str, run_id: str | None = None) -> TriageSummary:
    return triage.summary(dataset_id, run_id)


@router.post("/triage/simulate")
def simulate(req: SimulateTriageRequest) -> dict:
    try:
        return triage.simulate(req)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/triage")
def reset(dataset_id: str) -> dict:
    return {"removed": triage.reset(dataset_id)}
