"""Internal MCP server exposing the same tool catalogue to external agents (Claude Desktop, other apps)."""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable

import anyio

from app import config
from app.assistant import knowledge
from app.assistant import plain_language as pl
from app.assistant import tools as T
from app.mcp_compat import http_app, make_server

server = make_server(
    "inventory-sentinel",
    instructions=(
        "Tools over the Inventory Sentinel app: vendor connectors and syncs, inventory datasets, anomaly-detection models, detection runs and alerts, "
        "store/SKU drill-downs and live vendor stock lookups, investigation planning, team triage feedback, schedules, vendor tasks, SOPs and the user guide. "
        "Jobs (sync, train, detect, retrain, export, activate, schedules, vendor tasks) are proposals: propose_job returns a proposal that the user "
        "confirms in the app."
    ),
)


def as_thread_tool(fn: Callable[..., dict[str, Any]]) -> Callable[..., Any]:
    """MCP calls sync tools on the event loop; run them in a worker thread instead (heavy reads, vendor lookups)."""

    @functools.wraps(fn)
    async def wrapper(**kwargs: Any) -> dict[str, Any]:
        return await anyio.to_thread.run_sync(functools.partial(fn, **kwargs))

    wrapper.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
    return wrapper


for fn in T.CATALOGUE:
    server.tool()(as_thread_tool(fn))


@server.resource("sentinel://guide")
def guide_resource() -> str:
    """The Inventory Sentinel user guide (GUIDE.md)."""
    p = config.ROOT / "GUIDE.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


@server.resource("sentinel://readme")
def readme_resource() -> str:
    """The Inventory Sentinel README."""
    p = config.ROOT / "README.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


@server.resource("sentinel://glossary")
def glossary_resource() -> str:
    """Plain-language glossary of metrics, fields and algorithms."""
    return pl.glossary_markdown()


@server.resource("sentinel://story")
def story_resource() -> str:
    """The leadership story: how Inventory Sentinel works."""
    p = next((path for name, path in knowledge.DOCS if name == "Story"), None)
    return p.read_text(encoding="utf-8") if p and p.exists() else ""


@server.resource("sentinel://sops")
def sops_resource() -> str:
    """Index of the standard operating procedures for missing inventory, failed syncs and false alarms."""
    from app.services import sops

    return "\n".join(f"- {s.id}: {s.title} (v{s.version}) - {s.summary or ''}" for s in sops.list_sops())


@server.resource("sentinel://sop/{sop_id}")
def sop_resource(sop_id: str) -> str:
    """One standard operating procedure as Markdown (steps, escalation, closure)."""
    from app.services import sops

    return knowledge.sop_markdown(sops.get(sop_id))


mcp_app = http_app(server)
