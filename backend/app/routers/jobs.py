"""Background job status endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import Job
from app.services import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[Job])
def list_jobs(active: bool = False, type: str | None = None, limit: int = Query(50, ge=1, le=200)) -> list[Job]:  # noqa: A002
    return jobs.list_jobs(active_only=active, types=[type] if type else None, limit=limit)


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found (jobs are kept in memory until the server restarts).")
    return job


@router.post("/{job_id}/cancel")
def cancel(job_id: str) -> dict[str, bool]:
    return {"cancelled": jobs.cancel(job_id)}
