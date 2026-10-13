"""mcp 1.x (FastMCP) / 2.x (MCPServer) server shim; the mock must not import Sentinel's code, so it carries its own."""
from __future__ import annotations

from typing import Any, Callable


def make_server(name: str, instructions: str) -> Any:
    try:
        from mcp.server.mcpserver import MCPServer  # mcp >= 2

        return MCPServer(name, instructions=instructions)
    except ImportError:
        from mcp.server.fastmcp import FastMCP  # mcp 1.x

        return FastMCP(name, instructions=instructions, streamable_http_path="/", json_response=True, log_level="WARNING")


def add_tool(server: Any, fn: Callable[..., Any]) -> None:
    """Register a tool as plain JSON text: bulk pages must not be sent twice (text + structured copy)."""
    try:
        server.tool(structured_output=False)(fn)
    except TypeError:
        server.tool()(fn)


def http_app(server: Any) -> Any:
    try:
        return server.streamable_http_app(streamable_http_path="/", json_response=True)
    except TypeError:
        return server.streamable_http_app()
