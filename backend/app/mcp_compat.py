"""Bridge the mcp 1.x (FastMCP) and 2.x (MCPServer) Python SDKs, for both our MCP server and our MCP client.

requirements.txt asks for mcp 2.x, but many machines still carry 1.x; both expose the same streamable-HTTP transport.
"""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import threading
from datetime import timedelta
from typing import Any, AsyncIterator, Callable, Coroutine, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------- server
def make_server(name: str, instructions: str) -> Any:
    try:
        from mcp.server.mcpserver import MCPServer  # mcp >= 2

        return MCPServer(name, instructions=instructions)
    except ImportError:
        from mcp.server.fastmcp import FastMCP  # mcp 1.x

        return FastMCP(name, instructions=instructions, streamable_http_path="/", json_response=True, log_level="WARNING")


def http_app(server: Any) -> Any:
    """The streamable-HTTP ASGI app, served at the mount point's root ("/mcp/")."""
    try:
        return server.streamable_http_app(streamable_http_path="/", json_response=True)
    except TypeError:  # mcp 1.x takes these as constructor settings
        return server.streamable_http_app()


# ---------------------------------------------------------------- client
@contextlib.asynccontextmanager
async def client_session(url: str, headers: dict[str, str] | None = None, timeout: float = 60.0) -> AsyncIterator[Any]:
    """An initialized ClientSession over streamable HTTP."""
    from mcp import ClientSession

    try:
        from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

        # the SDK's own client defaults (30 s connect, 300 s read); mcp 2.x builds it on httpx2, so no httpx objects here
        http = create_mcp_http_client(headers=headers or {})
        cm = streamable_http_client(url, http_client=http)
    except ImportError:
        from mcp.client.streamable_http import streamablehttp_client  # older 1.x

        http = None
        cm = streamablehttp_client(url, headers=headers or {}, timeout=timeout)
    ann = str(inspect.signature(ClientSession.__init__).parameters["read_timeout_seconds"].annotation)
    read_timeout: Any = timedelta(seconds=timeout) if "timedelta" in ann else float(timeout)  # 1.x timedelta, 2.x float
    try:
        async with cm as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write, read_timeout_seconds=read_timeout) as session:
                await session.initialize()
                yield session
    finally:
        if http is not None:
            await http.aclose()


class ToolError(RuntimeError):
    """The remote tool reported an error (isError, or an {"error": {...}} payload)."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def result_payload(res: Any) -> Any:
    """structuredContent when present, else the JSON in the first text block; raise ToolError on tool errors."""
    structured = getattr(res, "structuredContent", None)
    if structured is None:
        structured = getattr(res, "structured_content", None)
    texts = [c.text for c in (res.content or []) if getattr(c, "text", None) is not None]
    if getattr(res, "isError", False) or getattr(res, "is_error", False):
        raise ToolError((texts[0] if texts else "The tool failed.")[:500])
    payload: Any = structured
    if isinstance(payload, dict) and set(payload) == {"result"}:  # FastMCP wraps non-object returns
        payload = payload["result"]
    if payload is None and texts:
        try:
            payload = json.loads(texts[0])
        except ValueError:
            payload = texts[0]
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        err = payload["error"]
        raise ToolError(str(err.get("message") or "The vendor reported an error."), err.get("code"))
    return payload


def run_sync(coro_factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run a coroutine from sync code: directly when this thread has no event loop, else in a fresh thread.

    Sync tools can be called from the job worker, FastAPI `def` endpoints, ADK (in a worker thread) or the MCP server
    (on the event loop), so never assume either. Every call builds its own client, so nothing crosses loops."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro_factory())
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=target, name="mcp-client", daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["value"]
