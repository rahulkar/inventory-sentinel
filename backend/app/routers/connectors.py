"""Vendor connector endpoints: add / test / sync connectors, live stock lookups and the vendor tasks Sentinel raised."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import Connector, ConnectorIn, ConnectorTest, Job, VendorTask
from app.services import connectors, jobs, sync, vendor_tasks

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


def _out(c: Connector) -> Connector:
    return connectors.to_out(c)


@router.get("", response_model=list[Connector])
def list_connectors() -> list[Connector]:
    return [_out(c) for c in connectors.list_all()]


@router.post("", response_model=Connector, status_code=201)
def create(body: ConnectorIn) -> Connector:
    c = connectors.create(body)
    res = connectors.test(c)
    if res.ok:
        connectors.patch(c.id, capabilities=res.capabilities, tested_at=connectors.storage.now_iso())
    return _out(connectors.get(c.id))


@router.post("/test", response_model=ConnectorTest)
def test_unsaved(body: ConnectorIn, connector_id: str | None = None) -> ConnectorTest:
    """Test a connector before saving it (a masked token reuses the saved connector's token)."""
    from app.assistant.settings import is_masked

    token = body.token or ""
    if connector_id and is_masked(body.token):
        token = connectors.get(connector_id).token
    c = Connector(id="conn_00000000", created_at="", **body.model_dump(exclude={"token"}), token=token)
    return connectors.test(c)


@router.get("/{connector_id}", response_model=Connector)
def get_connector(connector_id: str) -> Connector:
    return _out(connectors.get(connector_id))


@router.put("/{connector_id}", response_model=Connector)
def update(connector_id: str, body: ConnectorIn) -> Connector:
    return _out(connectors.update(connector_id, body))


@router.delete("/{connector_id}")
def delete(connector_id: str) -> dict[str, bool]:
    if [j for j in jobs.list_jobs(active_only=True) if j.params.get("connector_id") == connector_id]:
        raise HTTPException(409, "This connector is syncing; wait for it or cancel the job first.")
    from app.services import scheduler

    used = [s.name for s in scheduler.list_all() if s.connector_id == connector_id]
    if used:
        raise HTTPException(409, f"Schedules use this connector ({', '.join(used)}); delete or change them first.")
    if not connectors.delete(connector_id):
        raise HTTPException(404, "Connector not found.")
    return {"deleted": True}


@router.post("/{connector_id}/test", response_model=ConnectorTest)
def test_saved(connector_id: str) -> ConnectorTest:
    return connectors.refresh_capabilities(connector_id)


@router.post("/{connector_id}/sync", response_model=Job, status_code=202)
def start_sync(connector_id: str, full: bool = False) -> Job:
    try:
        return sync.start_job(connector_id, full)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{connector_id}/lookup")
def lookup(connector_id: str, store_id: str, sku_id: str, days: int = 7) -> dict:
    try:
        return connectors.stock_position(connector_id, store_id, sku_id, days)
    except connectors.ConnectorError as exc:
        raise HTTPException(502 if exc.kind != "vendor_error" else 400, str(exc)) from exc


@router.get("/{connector_id}/tasks", response_model=list[VendorTask])
def tasks(connector_id: str, status: str | None = None, refresh: bool = False) -> list[VendorTask]:
    if refresh:
        try:
            vendor_tasks.refresh(connectors.get(connector_id))
        except connectors.ConnectorError as exc:
            raise HTTPException(502, str(exc)) from exc
    return vendor_tasks.list_tasks(connector_id=connector_id, status=status)
