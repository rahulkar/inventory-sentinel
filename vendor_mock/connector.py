"""The demo vendor's MCP server: the "Sentinel Inventory Connector" contract v1 (see docs/connector-contract.md).

Every tool returns one JSON object; failures come back as {"error": {"code", "message"}} so a client can tell a vendor
error from a transport error. Bulk data is columnar and dictionary-encoded, paged with opaque keyset cursors.
"""
from __future__ import annotations

import functools
from typing import Any, Callable

import anyio

from vendor_mock import service, settings
from vendor_mock.mcp_compat import add_tool, http_app, make_server

server = make_server(
    "demo-vendor-backoffice",
    instructions=(
        f"{settings.VENDOR_NAME} inventory back-office, exposed through the Sentinel Inventory Connector contract v1: stores, SKUs, daily stock "
        "movements (columnar pages), loss-prevention flags, live stock positions and a task inbox Sentinel can write to. "
        "get_answer_key exists only because this is a simulated demo vendor."
    ),
)


def _tool(fn: Callable[..., dict[str, Any]]) -> Callable[..., Any]:
    @functools.wraps(fn)
    async def wrapper(**kwargs: Any) -> dict[str, Any]:
        try:
            return await anyio.to_thread.run_sync(functools.partial(fn, **kwargs))
        except service.VendorError as exc:
            return {"error": {"code": exc.code, "message": exc.message}}

    add_tool(server, wrapper)
    return wrapper


@_tool
def get_capabilities() -> dict[str, Any]:
    """What this vendor system supports: contract version, status (ready / seeding), date range, fields, paging limits, features and task types."""
    return service.capabilities()


@_tool
def list_stores(cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    """Stores: store_id, store_name, region, format, size_band, warehouse_team, footfall_index, opening hours. Paged with next_cursor."""
    return service.list_stores(cursor, page_size)


@_tool
def list_skus(cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    """SKUs: sku_id, sku_name, category, unit_cost, unit_price, high_theft_risk, security_tagged. Paged with next_cursor."""
    return service.list_skus(cursor, page_size)


@_tool
def get_daily_movements(since: str, until: str | None = None, fields: list[str] | None = None, cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    """Daily stock movements per store and SKU from `since` to `until` (ISO dates, inclusive; until defaults to the last closed day).

    Columnar JSON: `data` maps each column to an equal-length array; date / store_id / sku_id are {"dict": [...], "idx": [...]}.
    Rows are ordered by (date, store_id, sku_id). Pass `next_cursor` back (same arguments) until it is null."""
    return service.daily_movements(since, until, fields, cursor, page_size)


@_tool
def get_lp_flags(since: str | None = None, until: str | None = None, cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    """Loss-prevention flags reported so far for days in [since, until]: flag_id, date, store_id, sku_id, flag_type, source, confirmed, loss_value_gbp, reported_on."""
    return service.lp_flags(since, until, cursor, page_size)


@_tool
def get_stock_position(store_id: str, sku_id: str, days: int = 7) -> dict[str, Any]:
    """Live stock position of one SKU in one store: on-hand count and the last `days` (max 14) of movements."""
    return service.stock_position(store_id, sku_id, days)


@_tool
def create_task(
    type: str, store_id: str, title: str, description: str = "", priority: str = "normal", idempotency_key: str | None = None,
    sku_id: str | None = None, external_ref: str | None = None, source_alert_id: str | None = None, sop_id: str | None = None,
    evidence: dict[str, Any] | None = None, due_by: str | None = None,
) -> dict[str, Any]:
    """Raise a task for store staff (recount, investigate, cctv_review, receiving_check, till_audit, data_correction, process_review).

    Repeating a call with the same idempotency_key returns the existing task instead of creating a second one."""
    return service.create_task(type, store_id, title, description, priority, idempotency_key, sku_id, external_ref, source_alert_id, sop_id, evidence, due_by)


@_tool
def list_tasks(status: str | None = None, store_id: str | None = None, external_ref: str | None = None, updated_since: str | None = None, cursor: str | None = None, page_size: int | None = 100) -> dict[str, Any]:
    """Tasks (newest updates last), optionally filtered; includes status, outcome (confirmed_loss / count_corrected / process_fixed / no_issue) and notes."""
    return service.list_tasks(status, store_id, external_ref, updated_since, cursor, page_size)


@_tool
def get_task(task_id: str) -> dict[str, Any]:
    """One task with its full event history."""
    return service.get_task(task_id)


@_tool
def get_answer_key(since: str | None = None, until: str | None = None, cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
    """DEMO ONLY: the anomalies injected into this simulated estate (columnar, like get_daily_movements), for scoring detectors."""
    return service.answer_key(since, until, cursor, page_size)


mcp_app = http_app(server)
