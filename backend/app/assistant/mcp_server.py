"""Internal MCP server exposing the same tool catalogue to external agents (Claude Desktop, other apps)."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from app.assistant import knowledge
from app.assistant import plain_language as pl
from app.assistant import tools as T
from app import config

server = MCPServer(
    "inventory-sentinel",
    instructions=(
        "Tools over the Inventory Sentinel app: inventory datasets, anomaly-detection models, detection runs and alerts, store/SKU drill-downs, "
        "investigation planning, team triage feedback and the user guide. Jobs (generate, train, detect, retrain, export, activate) are proposals: "
        "propose_job returns a proposal that the user confirms in the app's chat UI."
    ),
)

for fn in T.CATALOGUE:
    server.tool()(fn)


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


mcp_app = server.streamable_http_app(streamable_http_path="/", json_response=True)
