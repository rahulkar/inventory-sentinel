"""Vendor connectors: where Sentinel reads inventory from (and writes approved tasks to) over MCP.

A connector is a vendor's MCP server that implements the Sentinel Inventory Connector contract (docs/connector-contract.md).
Connectors are stored in data/connectors.json; tokens are masked in every API response, tool result and prompt.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from app import config
from app.mcp_compat import ToolError, client_session, result_payload, run_sync
from app.schemas import Connector, ConnectorIn, ConnectorSync, ConnectorTest
from app.services import storage

CONTRACT = "sentinel-inventory-connector"
_lock = threading.RLock()
_cache: list[Connector] | None = None


class ConnectorError(RuntimeError):
    """The vendor could not be reached or answered with an error; `kind` feeds the data-feed-failure SOP."""

    def __init__(self, message: str, kind: str = "unreachable") -> None:
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------- persistence
def _load() -> list[Connector]:
    global _cache
    if _cache is None:
        items: list[Connector] = []
        if config.CONNECTORS_PATH.exists():
            try:
                for d in json.loads(config.CONNECTORS_PATH.read_text(encoding="utf-8")):
                    try:
                        items.append(Connector(**d))
                    except ValueError:
                        continue
            except ValueError:
                pass
        _cache = items
    return _cache


def _save() -> None:
    config.ensure_dirs()
    storage.atomic_write_text(config.CONNECTORS_PATH, json.dumps([c.model_dump() for c in _load()], indent=1))


def list_all() -> list[Connector]:
    with _lock:
        return [c.model_copy(deep=True) for c in _load()]


def get(connector_id: str | None) -> Connector:
    with _lock:
        items = _load()
        if not connector_id:
            enabled = [c for c in items if c.enabled]
            if len(enabled) == 1:
                return enabled[0].model_copy(deep=True)
            raise LookupError("Name a connector: there are " + (f"{len(enabled)} enabled connectors." if enabled else "no connectors yet. Add one on the Data page."))
        for c in items:
            if c.id == connector_id:
                return c.model_copy(deep=True)
    raise LookupError(f"Connector {connector_id} not found.")


def _mask(token: str) -> str:
    from app.assistant.settings import mask

    return mask(token)


def to_out(c: Connector) -> Connector:
    out = c.model_copy(deep=True)
    out.token = _mask(c.token) if c.token else ""
    return out


def create(body: ConnectorIn) -> Connector:
    from app.assistant.settings import is_masked

    c = Connector(id=storage.new_id("conn"), created_at=storage.now_iso(), **body.model_dump(exclude={"token"}), token="" if is_masked(body.token) else (body.token or "").strip())
    with _lock:
        _load().append(c)
        _save()
    return c.model_copy(deep=True)


def update(connector_id: str, body: ConnectorIn) -> Connector:
    from app.assistant.settings import is_masked

    with _lock:
        items = _load()
        for i, c in enumerate(items):
            if c.id == connector_id:
                data = c.model_dump()
                data.update(body.model_dump(exclude={"token"}))
                if not is_masked(body.token):
                    data["token"] = (body.token or "").strip()
                elif body.token == "":
                    data["token"] = ""
                if data["url"] != c.url:
                    data["capabilities"] = None
                items[i] = Connector(**data)
                _save()
                return items[i].model_copy(deep=True)
    raise LookupError(f"Connector {connector_id} not found.")


def patch(connector_id: str, **fields: Any) -> None:
    with _lock:
        for c in _load():
            if c.id == connector_id:
                for k, v in fields.items():
                    setattr(c, k, v)
                _save()
                return


def delete(connector_id: str) -> bool:
    with _lock:
        items = _load()
        keep = [c for c in items if c.id != connector_id]
        if len(keep) == len(items):
            return False
        items[:] = keep
        _save()
    storage.safe_rmtree(config.CONNECTORS_DIR / storage.check_id(connector_id))
    return True


def record_sync(connector_id: str, sync: ConnectorSync) -> None:
    patch(connector_id, last_sync=sync)


def ensure_default() -> Connector | None:
    """Register SENTINEL_DEFAULT_CONNECTOR_URL (the demo vendor in dev scripts) when no connector exists yet."""
    if not config.DEFAULT_CONNECTOR_URL:
        return None
    with _lock:
        if _load():
            return None
    import os

    c = create(ConnectorIn(name=os.environ.get("SENTINEL_DEFAULT_CONNECTOR_NAME", "Demo vendor (simulated)"), url=config.DEFAULT_CONNECTOR_URL, token=os.environ.get("SENTINEL_DEFAULT_CONNECTOR_TOKEN") or None))
    print(f"[startup] registered connector {c.name} at {c.url}")
    return c


# ---------------------------------------------------------------- MCP calls
def headers(c: Connector) -> dict[str, str]:
    if not c.token:
        return {}
    value = f"{c.auth_scheme} {c.token}".strip() if c.auth_scheme else c.token
    return {c.auth_header or "Authorization": value}


def leaf(exc: BaseException) -> BaseException:
    """anyio task groups (inside the MCP client) wrap the real cause in exception groups."""
    while getattr(exc, "exceptions", None):
        exc = exc.exceptions[0]  # type: ignore[attr-defined]
    return exc


def _friendly(exc: BaseException, c: Connector) -> ConnectorError:
    exc = leaf(exc)
    if isinstance(exc, ConnectorError):
        return exc
    if isinstance(exc, ToolError):
        kind = "not_ready" if exc.code == "not_ready" else "vendor_error"
        return ConnectorError(f"{c.name}: {exc}", kind)
    text = f"{type(exc).__name__}: {exc}"
    low = text.lower()
    if "401" in low or "403" in low or "unauthorized" in low:
        return ConnectorError(f"{c.name} refused the credentials (check the token).", "auth")
    if "timeout" in low or "timed out" in low:
        return ConnectorError(f"{c.name} did not answer in time ({text[:160]}).", "timeout")
    return ConnectorError(f"Could not reach {c.name} at {c.url} ({text[:200]}).", "unreachable")


async def call_many(c: Connector, calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    """Several tool calls over one MCP session (inside a coroutine)."""
    out = []
    async with client_session(c.url, headers(c), config.MCP_CALL_TIMEOUT_S) as s:
        for name, args in calls:
            out.append(result_payload(await s.call_tool(name, {k: v for k, v in args.items() if v is not None})))
    return out


async def _each(c: Connector, calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    out: list[Any] = []
    async with client_session(c.url, headers(c), config.MCP_CALL_TIMEOUT_S) as s:
        for name, args in calls:
            try:
                out.append(result_payload(await s.call_tool(name, {k: v for k, v in args.items() if v is not None})))
            except ToolError as exc:  # one rejected item must not fail the batch
                out.append(_friendly(exc, c))
    return out


def call_each(c: Connector, calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    """Several calls over one session; each result is the payload or a ConnectorError for that call."""
    try:
        return run_sync(lambda: _each(c, calls))
    except BaseException as exc:  # noqa: BLE001
        raise _friendly(exc, c) from exc


def call(c: Connector, name: str, args: dict[str, Any] | None = None) -> Any:
    """One tool call from sync code."""
    try:
        return run_sync(lambda: call_many(c, [(name, args or {})]))[0]
    except BaseException as exc:  # noqa: BLE001
        raise _friendly(exc, c) from exc


def test(c: Connector) -> ConnectorTest:
    t0 = time.time()
    try:
        caps = call(c, "get_capabilities")
    except ConnectorError as exc:
        return ConnectorTest(ok=False, error=str(exc), seconds=round(time.time() - t0, 2))
    if not isinstance(caps, dict) or caps.get("contract") != CONTRACT:
        return ConnectorTest(ok=False, capabilities=caps if isinstance(caps, dict) else None, error=f"The server answered but does not implement the {CONTRACT} contract.", seconds=round(time.time() - t0, 2))
    return ConnectorTest(ok=True, capabilities=caps, seconds=round(time.time() - t0, 2))


def refresh_capabilities(connector_id: str) -> ConnectorTest:
    c = get(connector_id)
    res = test(c)
    if res.ok:
        patch(connector_id, capabilities=res.capabilities, tested_at=storage.now_iso())
    return res


def stock_position(connector_id: str | None, store_id: str, sku_id: str, days: int = 7) -> dict[str, Any]:
    c = get(connector_id)
    if not ((c.capabilities or {}).get("features") or {}).get("live_lookup", True):
        raise ConnectorError(f"{c.name} does not offer live stock lookups.", "unsupported")
    return call(c, "get_stock_position", {"store_id": store_id, "sku_id": sku_id, "days": days})


def connector_datasets(connector_id: str) -> list[Any]:
    return [d for d in storage.list_datasets() if (d.params or {}).get("connector_id") == connector_id]
