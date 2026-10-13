"""AI gateway settings endpoints. The secret key is stored server-side and only ever returned masked."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.assistant import settings as llm
from app.assistant import usage
from app.assistant.settings import LlmSettingsOut, LlmTestRequest, LlmTestResult

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _invalidate_engine() -> None:
    try:
        from app.assistant.engine import engine

        engine.invalidate()
    except Exception:  # noqa: BLE001 - engine optional (packages missing)
        pass


@router.get("/llm", response_model=LlmSettingsOut)
def get_llm() -> LlmSettingsOut:
    return llm.to_out(llm.load())


@router.put("/llm", response_model=LlmSettingsOut)
def put_llm(body: dict[str, Any] = Body(...)) -> LlmSettingsOut:
    try:
        merged = llm.merge_put(llm.load(), body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if isinstance(body.get("embedding_model"), str):
        merged.embedding_model = body["embedding_model"].strip()
    saved = llm.save(merged)
    _invalidate_engine()
    if saved.embedding_model:
        from app.services import documents

        documents.start_embedding()  # a new (or first) embedding model: embed the library in the background now
    return llm.to_out(saved)


@router.post("/llm/test", response_model=LlmTestResult)
async def test_llm(req: LlmTestRequest) -> LlmTestResult:
    stored = llm.load()
    base = llm.normalise_base_url(req.base_url) if req.base_url else stored.base_url
    key = stored.api_key if llm.is_masked(req.api_key) else (req.api_key or "").strip()
    model = req.model if req.model is not None else stored.model
    verify = llm.verify_arg(stored.verify_ssl if req.verify_ssl is None else req.verify_ssl, stored.ca_bundle if req.ca_bundle is None else req.ca_bundle)
    return await llm.probe(base, key, model or None, want_chat=bool(model), verify=verify)


@router.get("/llm/models")
async def llm_models() -> dict[str, list[str]]:
    s = llm.load()
    if not s.base_url:
        raise HTTPException(400, "Gateway URL is not configured.")
    try:
        return {"models": await llm.list_models(s.base_url, s.api_key, verify=llm.verify_arg(s.verify_ssl, s.ca_bundle))}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, llm.readable_error(exc, s.base_url)) from exc


@router.get("/finops")
def finops() -> dict[str, Any]:
    """AI spend for the FinOps card: periods, budget, chat vs embeddings, per agent, last 30 days."""
    return usage.finops(llm.load().monthly_budget_usd)


@router.put("/finops/budget")
def put_budget(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Set the monthly budget alone (no engine rebuild, gateway fields untouched)."""
    try:
        amount = float(body.get("monthly_budget_usd") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "monthly_budget_usd must be a number.") from exc
    if amount < 0:
        raise HTTPException(400, "The budget cannot be negative.")
    s = llm.load().model_copy()
    s.monthly_budget_usd = amount
    llm.save(s)
    return usage.finops(amount)
