"""SOP and vendor-task endpoints: the procedures for an alert, and raising approved tasks from the drill-down."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import AlertSop, Sop, SopSummary, VendorTask, VendorTaskRequest
from app.services import sops, vendor_tasks

router = APIRouter(tags=["sops"])


@router.get("/api/sops", response_model=list[SopSummary])
def list_sops() -> list[SopSummary]:
    return sops.list_sops()


@router.get("/api/sops/{sop_id}", response_model=Sop)
def get_sop(sop_id: str) -> Sop:
    return sops.get(sop_id)


@router.get("/api/runs/{run_id}/alerts/{alert_id}/sop", response_model=AlertSop)
def alert_sop(run_id: str, alert_id: str) -> AlertSop:
    return sops.for_alert(run_id, alert_id)


@router.get("/api/vendor-tasks", response_model=list[VendorTask])
def list_vendor_tasks(alert_key: str | None = None, run_id: str | None = None, connector_id: str | None = None, status: str | None = None, limit: int = 200) -> list[VendorTask]:
    return vendor_tasks.list_tasks(connector_id=connector_id, status=status, alert_key=alert_key, run_id=run_id, limit=max(1, min(limit, 1000)))


@router.post("/api/vendor-tasks")
def raise_vendor_tasks(body: VendorTaskRequest) -> dict[str, Any]:
    """The drill-down's confirm dialog: the person pressing Confirm is the approval."""
    res = vendor_tasks.create(body.tasks, source="ui", connector_id=body.connector_id)
    if not res["created"] and not res["existing"] and res["failed"]:
        raise HTTPException(502, "; ".join(f["error"] for f in res["failed"]))
    return res
