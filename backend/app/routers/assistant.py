"""Assistant endpoints: status, streaming chat (SSE), sessions, proposals."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.assistant import proposals, usage
from app.assistant.engine import AssistantStatus, ChatMessage, ChatRequest, SessionSummary, engine
from app.assistant.proposals import Proposal, ProposalError
from app.schemas import Job

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/status", response_model=AssistantStatus)
def status() -> AssistantStatus:
    return engine.status()


def _sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8")


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    if not req.message.strip():
        raise HTTPException(400, "Message is empty.")
    if len(req.message) > 4000:
        raise HTTPException(400, "Message is too long (4,000 characters max).")
    abort = asyncio.Event()

    async def watch_disconnect() -> None:
        try:
            while not abort.is_set():
                if await request.is_disconnected():
                    abort.set()
                    return
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return

    async def gen() -> AsyncIterator[bytes]:
        watcher = asyncio.create_task(watch_disconnect())
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def produce() -> None:
            try:
                async for ev in engine.chat(req, abort):
                    await queue.put(ev)
            except Exception as exc:  # noqa: BLE001
                await queue.put({"event": "error", "data": {"code": "server_error", "message": str(exc)[:300]}})
            finally:
                await queue.put(None)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield b": ping\n\n"
                    continue
                if ev is None:
                    break
                yield _sse(ev["event"], ev["data"])
        finally:
            abort.set()
            watcher.cancel()
            if not producer.done():
                producer.cancel()

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@router.get("/sessions", response_model=list[SessionSummary])
async def sessions() -> list[SessionSummary]:
    ok, reason = engine.available()
    if not ok:
        return []
    return await engine.list_sessions()


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessage])
async def messages(session_id: str) -> list[ChatMessage]:
    try:
        return await engine.get_messages(session_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, bool]:
    try:
        await engine.delete_session(session_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Could not delete: {exc}") from exc
    return {"deleted": True}


@router.get("/proposals", response_model=list[Proposal])
def list_proposals(session_id: str | None = None) -> list[Proposal]:
    return proposals.list_for_session(session_id)


@router.post("/proposals/{proposal_id}/confirm")
def confirm(proposal_id: str) -> dict[str, Any]:
    try:
        out = proposals.execute(proposal_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProposalError as exc:
        raise HTTPException(409, str(exc)) from exc
    job = out.get("job")
    return {"proposal": out["proposal"].model_dump(), "job": job.model_dump() if isinstance(job, Job) else None, "result": out.get("result")}


@router.post("/proposals/{proposal_id}/cancel")
def cancel(proposal_id: str) -> dict[str, Any]:
    try:
        return {"proposal": proposals.cancel(proposal_id).model_dump()}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/usage")
def usage_report(session_id: str | None = None) -> dict[str, Any]:
    """Agents in the system with invocations, LLM calls, tool calls, tokens and estimated cost (all time or one conversation)."""
    return usage.full_report(session_id)


@router.delete("/usage")
def usage_reset() -> dict[str, bool]:
    usage.reset()
    return {"reset": True}
