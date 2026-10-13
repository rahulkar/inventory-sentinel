"""Inventory Sentinel API. Run with: uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000"""
from __future__ import annotations

import os
import platform
from contextlib import asynccontextmanager

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("LITELLM_TELEMETRY", "False")
os.environ.setdefault("ADK_DISABLE_TELEMETRY", "1")

from app import compat  # noqa: E402

compat.install()  # before anything imports SQLAlchemy (assistant sessions)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app import config  # noqa: E402
from app.assistant import proposals  # noqa: E402
from app.routers import assistant, connectors as connectors_router, datasets, documents as documents_router, jobs, planner, runs, schedules, settings, sops, training  # noqa: E402
from app.schemas import AppConfig, Health  # noqa: E402
from app.services import connectors, envprobe, registry, scheduler, storage  # noqa: E402

try:
    from app.assistant.mcp_server import mcp_app, server as mcp_server

    MCP_REASON: str | None = None
except Exception as exc:  # noqa: BLE001 - keep the app usable if the mcp package is missing/blocked
    mcp_app = None
    mcp_server = None
    MCP_REASON = f"{type(exc).__name__}: {exc}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.ensure_dirs()
    removed = storage.sweep_orphans()
    if removed:
        print(f"[startup] removed {len(removed)} orphaned item(s) from data/")
    proposals.load()
    try:
        connectors.ensure_default()
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] could not register the default connector: {exc}")
    issues, engines = envprobe.report()
    for i in issues:
        print(f"[startup] {i}")
    print("[startup] engines: " + ", ".join(f"{k}={v}" for k, v in engines.items()))
    from app.assistant import settings as llm_settings

    tls = llm_settings.load()
    if tls.verify_ssl:
        print("[startup] AI gateway TLS certificates are verified " + (f"against the CA bundle {tls.ca_bundle}" if tls.ca_bundle else "against the system store"))
    else:
        print("[startup] AI gateway TLS certificate verification is off (default for lab gateways; switch on in Settings or LITELLM_SSL_VERIFY=true)")
    if os.environ.get("SENTINEL_SCHEDULER", "on").lower() not in ("0", "off", "false", "no"):
        scheduler.start()
    # google-adk and litellm are imported lazily on the first chat, on the event-loop thread
    try:
        if mcp_server is not None:
            async with mcp_server.session_manager.run():
                yield
        else:
            yield
    finally:
        scheduler.stop()
    try:
        from app.assistant.engine import engine

        await engine.close()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="Inventory Sentinel", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


def _version(module: str) -> str | None:
    try:
        from importlib import metadata

        return metadata.version(module)
    except Exception:  # noqa: BLE001
        return None


@app.get("/api/health", response_model=Health, tags=["misc"])
def health() -> Health:
    issues, engines = envprobe.report()
    return Health(
        status="ok",
        versions={
            "python": platform.python_version(), "numpy": _version("numpy"), "pandas": _version("pandas"), "scikit-learn": _version("scikit-learn"),
            "lightgbm": _version("lightgbm"), "onnx": _version("onnx"), "onnxruntime": _version("onnxruntime"),
            "google-adk": _version("google-adk"), "litellm": _version("litellm"), "mcp": _version("mcp") if mcp_app is not None else None,
        },
        data_dir=str(config.DATA_DIR),
        env_issues=issues + ([f"MCP server unavailable: {MCP_REASON}"] if MCP_REASON else []),
        engines=engines,
    )


@app.get("/api/config", response_model=AppConfig, tags=["misc"])
def app_config() -> AppConfig:
    timing = dict(config.TIMING)
    for key, spec in registry.REGISTRY.items():
        timing[f"model_{key}_fit_s"] = spec.fit_seconds
        timing[f"model_{key}_score_s_per_1m"] = spec.score_seconds_per_1m
    return AppConfig(
        max_rows=config.MAX_ROWS, max_upload_mb=config.MAX_UPLOAD_MB, default_train_sample=config.DEFAULT_TRAIN_SAMPLE, quick_train_sample=config.QUICK_TRAIN_SAMPLE,
        default_alert_rate=config.DEFAULT_ALERT_RATE, planner_defaults=config.PLANNER_DEFAULTS, minutes_by_type=config.MINUTES_BY_TYPE,
        persist_by_type=config.PERSIST_BY_TYPE, triage_outcomes=config.TRIAGE_OUTCOMES, anomaly_types=config.ANOMALY_TYPES[1:] + ["unclear"],
        categories=config.CATEGORIES, timing=timing,
    )


@app.exception_handler(connectors.ConnectorError)
async def vendor_unreachable(_: Request, exc: connectors.ConnectorError) -> JSONResponse:
    """The vendor system could not be reached or refused the request."""
    return JSONResponse({"detail": str(exc), "kind": exc.kind}, status_code=502)


@app.exception_handler(LookupError)
async def not_found(_: Request, exc: LookupError) -> JSONResponse:
    """An unknown (or malformed) dataset / model / run id is a 404 on every route, not a 500."""
    return JSONResponse({"detail": str(exc)}, status_code=404)


for r in (datasets.router, connectors_router.router, schedules.router, sops.router, documents_router.router, training.router, runs.router, planner.router, jobs.router, settings.router, assistant.router):
    app.include_router(r)

if mcp_app is not None:
    app.mount("/mcp", mcp_app)  # served at /mcp/ ; must precede the SPA catch-all

    @app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
    def mcp_redirect() -> RedirectResponse:
        return RedirectResponse(url="/mcp/", status_code=307)

if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        dist = config.FRONTEND_DIST.resolve()
        candidate = (dist / full_path).resolve()
        # only files inside dist: "..%2F" or an absolute path would otherwise reach data/settings.json (the gateway key)
        if full_path and candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(config.FRONTEND_DIST / "index.html")
