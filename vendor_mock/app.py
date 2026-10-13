"""Demo vendor back-office: a simulated retailer's inventory system that Sentinel reaches over MCP.

Run from the repo root:  python -m uvicorn vendor_mock.app:app --host 127.0.0.1 --port 8020
"""
from __future__ import annotations

import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from vendor_mock import db, seed, service, settings, ui
from vendor_mock.connector import mcp_app, server


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    if seed.start_background():
        print(f"[vendor] seeding {settings.N_STORES} stores x {settings.N_SKUS} SKUs x {settings.HISTORY_DAYS + settings.FUTURE_DAYS} days into {settings.DB_PATH}")
    async with server.session_manager.run():
        yield


app = FastAPI(title=f"{settings.VENDOR_NAME} back-office (demo)", lifespan=lifespan)


@app.middleware("http")
async def mcp_auth(request: Request, call_next):
    if settings.TOKEN and request.url.path.startswith("/mcp"):
        got = request.headers.get("authorization", "")
        if not hmac.compare_digest(got, f"Bearer {settings.TOKEN}"):
            return JSONResponse({"error": {"code": "unauthorized", "message": "A valid bearer token is required."}}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    st = seed.status()
    out = {"status": "ok", "data": st["status"], "progress": st["progress"]}
    if st["status"] == "ready":
        out.update(service.clock())
    return out


@app.post("/api/advance")
def api_advance(days: int = 1) -> dict:
    """Fast-forward the business clock (also used by tests)."""
    return service.advance(days)


app.include_router(ui.router)
app.mount("/mcp", mcp_app)


@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
def mcp_redirect() -> RedirectResponse:
    return RedirectResponse(url="/mcp/", status_code=307)
