"""Schedule endpoints: CRUD, run now, run history, engine status and approvals waiting from scheduled runs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import Schedule, ScheduleIn, SchedulerStatus, ScheduleRun
from app.services import scheduler

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _validated(fn, *args):
    try:
        return fn(*args)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("", response_model=list[Schedule])
def list_schedules() -> list[Schedule]:
    return scheduler.list_all()


@router.get("/status", response_model=SchedulerStatus)
def status() -> SchedulerStatus:
    return scheduler.status()


@router.get("/runs", response_model=list[ScheduleRun])
def all_runs(limit: int = 50) -> list[ScheduleRun]:
    return scheduler.list_runs(None, limit=max(1, min(limit, 500)))


@router.get("/pending-approvals")
def pending_approvals() -> list[dict[str, Any]]:
    from app.assistant import proposals

    return [p.model_dump() for p in proposals.list_pending(source="scheduler")]


@router.post("", response_model=Schedule, status_code=201)
def create(body: ScheduleIn) -> Schedule:
    return _validated(scheduler.create, body)


@router.post("/preview")
def preview(body: ScheduleIn) -> dict[str, Any]:
    """Plain-language summary and the next few run times, for the editor."""
    from datetime import timedelta

    s = _validated(scheduler.validate, body)
    tmp = scheduler.Schedule(id="sch_00000000", created_at="", updated_at="", **s.model_dump())
    t = scheduler._utcnow()
    nxt = []
    for _ in range(3):
        t = scheduler.next_run(tmp, t)
        nxt.append(scheduler._iso(t))
        t = t + timedelta(seconds=1)
    return {"summary": scheduler.describe(tmp), "next_runs": nxt}


@router.get("/{schedule_id}", response_model=Schedule)
def get_schedule(schedule_id: str) -> Schedule:
    return scheduler.get(schedule_id)


@router.put("/{schedule_id}", response_model=Schedule)
def update(schedule_id: str, body: ScheduleIn) -> Schedule:
    return _validated(scheduler.update, schedule_id, body)


@router.post("/{schedule_id}/enabled", response_model=Schedule)
def set_enabled(schedule_id: str, enabled: bool) -> Schedule:
    return _validated(scheduler.set_enabled, schedule_id, enabled)


@router.delete("/{schedule_id}")
def delete(schedule_id: str) -> dict[str, bool]:
    if not scheduler.delete(schedule_id):
        raise HTTPException(404, "Schedule not found.")
    return {"deleted": True}


@router.post("/{schedule_id}/run")
def run_now(schedule_id: str) -> dict[str, Any]:
    run, job = scheduler.run_now(schedule_id)
    return {"run": run.model_dump(), "job": job.model_dump() if job else None}


@router.get("/{schedule_id}/runs", response_model=list[ScheduleRun])
def runs(schedule_id: str, limit: int = 30) -> list[ScheduleRun]:
    return scheduler.list_runs(schedule_id, limit=max(1, min(limit, 500)))
