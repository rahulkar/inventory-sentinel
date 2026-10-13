"""AssistantEngine: lazy ADK/LiteLLM setup, runner lifecycle, SSE event mapping, session persistence."""
from __future__ import annotations

import asyncio
import inspect
import json
import time
import traceback
from typing import Any, AsyncIterator

from pydantic import BaseModel

from app import config
from app.assistant import proposals
from app.assistant import settings as llm_settings
from app.assistant import usage
from app.assistant.adk_tools import tool_label
from app.assistant.context_pack import UiState
from app.services import storage

APP_NAME = "inventory_sentinel"
USER_ID = "local"


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    ui: UiState = UiState()


class AssistantStatus(BaseModel):
    available: bool
    reason: str | None = None
    configured: bool
    model: str
    base_host: str
    agent_mode: str
    streaming: bool
    engine_ready: bool
    last_error: str | None = None
    versions: dict[str, str | None] = {}


class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: str | None = None
    updated_at: str | None = None
    n_messages: int = 0


class ToolActivity(BaseModel):
    id: str | None = None
    name: str
    label: str
    ok: bool | None = None
    summary: str | None = None
    author: str | None = None


class ChatMessage(BaseModel):
    id: str
    role: str  # user | assistant | system
    author: str | None = None
    text: str
    tools: list[ToolActivity] = []
    proposals: list[dict[str, Any]] = []
    timestamp: float | None = None


def _version(dist: str) -> str | None:
    try:
        from importlib import metadata

        return metadata.version(dist)
    except Exception:  # noqa: BLE001
        return None


def _summarise_result(name: str, resp: Any) -> tuple[bool, str]:
    if not isinstance(resp, dict):
        return True, str(resp)[:120]
    if resp.get("status") == "error":
        return False, str(resp.get("error_message", "error"))[:200]
    if name == "list_datasets":
        return True, f"{resp.get('count', 0)} datasets"
    if name == "list_models":
        return True, f"{resp.get('count', 0)} models"
    if name == "list_detection_runs":
        return True, f"{resp.get('count', 0)} runs"
    if name == "alert_summary":
        return True, f"{resp.get('alerts', 0):,} alerts, £{resp.get('value_at_risk_gbp', 0):,.0f} at risk"
    if name == "list_alerts":
        return True, f"{resp.get('total_matching', 0):,} matching, {len(resp.get('alerts') or [])} shown"
    if name == "explain_alert":
        return True, f"{resp.get('alert_id')}: {resp.get('likely_type')}, £{resp.get('value_at_risk_gbp', 0):,.0f}"
    if name == "sku_drilldown":
        return True, f"{resp.get('flagged_days', 0)} flagged days, {len(resp.get('alerts') or [])} alerts"
    if name == "investigation_plan":
        return True, f"{resp.get('alerts_selected', 0):,} alerts, £{resp.get('expected_recovered_gbp', 0):,.0f} expected"
    if name == "compare_plans":
        return True, f"{len(resp.get('plans') or [])} budgets compared"
    if name == "triage_summary":
        return True, f"{resp.get('reviewed', 0)} reviewed, precision {resp.get('precision')}"
    if name in ("hotspots", "anomaly_trend"):
        return True, "ok"
    if name == "propose_job":
        return True, str((resp.get("proposal") or {}).get("title", "proposed"))
    if name == "search_docs":
        return True, f"{resp.get('count', 0)} passages"
    if name == "job_status":
        return True, f"{resp.get('n_active', 0)} active"
    return True, "ok"


class AssistantEngine:
    def __init__(self) -> None:
        self._avail: tuple[bool, str | None] | None = None
        self._runner: Any = None
        self._fingerprint: str | None = None
        self._session_service: Any = None
        self._build_lock = asyncio.Lock()
        self._session_locks: dict[str, asyncio.Lock] = {}
        self.last_error: str | None = None
        self._price: dict[str, Any] | None = None
        self._model_id: str = ""

    # ------------------------------------------------------------ availability
    def available(self) -> tuple[bool, str | None]:
        if self._avail is not None:
            return self._avail
        try:
            import litellm  # noqa: F401
            from google.adk.agents import LlmAgent  # noqa: F401
            from google.adk.models.lite_llm import LiteLlm  # noqa: F401
            from google.adk.runners import Runner  # noqa: F401
            from app.assistant import agents  # noqa: F401

            self._avail = (True, None)
        except Exception as exc:  # noqa: BLE001
            self._avail = (False, f"{type(exc).__name__}: {exc}")
        return self._avail

    def status(self) -> AssistantStatus:
        s = llm_settings.load()
        avail, reason = self._avail if self._avail is not None else (True, None)
        host = s.base_url.split("//", 1)[-1].split("/", 1)[0] if s.base_url else ""
        return AssistantStatus(
            available=avail,
            reason=reason,
            configured=s.configured,
            model=s.model,
            base_host=host,
            agent_mode=s.agent_mode,
            streaming=s.streaming,
            engine_ready=self._runner is not None,
            last_error=self.last_error,
            versions={"google-adk": _version("google-adk"), "litellm": _version("litellm"), "mcp": _version("mcp")},
        )

    def invalidate(self) -> None:
        self._fingerprint = None

    async def close(self) -> None:
        runner, self._runner = self._runner, None
        if runner is not None:
            try:
                await runner.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ runner / sessions
    async def session_service(self) -> Any:
        if self._session_service is None:
            try:
                from google.adk.sessions import DatabaseSessionService

                config.ensure_dirs()
                db = str(config.ASSISTANT_DB).replace("\\", "/")
                self._session_service = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{db}")
            except Exception as exc:  # noqa: BLE001 - e.g. SQLAlchemy blocked by application control
                from google.adk.sessions import InMemorySessionService

                print(f"[assistant] conversations kept in memory only (database unavailable: {type(exc).__name__}: {str(exc)[:160]})")
                self._session_service = InMemorySessionService()
        return self._session_service

    async def _ensure_runner(self) -> Any:
        s = llm_settings.load()
        fp = s.fingerprint()
        if self._runner is not None and fp == self._fingerprint:
            return self._runner
        async with self._build_lock:
            if self._runner is not None and fp == self._fingerprint:
                return self._runner
            ok, reason = self.available()
            if not ok:
                raise RuntimeError(f"Assistant unavailable: {reason}")
            if not s.configured:
                raise RuntimeError("not_configured")
            from google.adk.models.lite_llm import LiteLlm
            from google.adk.runners import Runner

            from app.assistant.agents import build_agent_tree

            await self.close()
            import litellm

            # One gateway per app, so the TLS choice is global for litellm: True, False or a CA bundle path.
            litellm.ssl_verify = llm_settings.verify_arg(s.verify_ssl, s.ca_bundle)
            model = LiteLlm(
                model=f"openai/{s.model}",
                api_base=f"{s.base_url}/v1",
                api_key=s.api_key or "no-key",
                timeout=s.timeout_s,
                drop_params=True,
            )
            agent = build_agent_tree(model, s)
            self._runner = Runner(app_name=APP_NAME, agent=agent, session_service=await self.session_service())
            self._fingerprint = fp
            self._model_id = s.model
            await usage.fetch_gateway_prices(s.base_url, s.api_key, verify=llm_settings.verify_arg(s.verify_ssl, s.ca_bundle))  # best effort
            self._price = usage.resolve_price(s.base_url, s.model, s.price_input_per_m, s.price_output_per_m)
            self.last_error = None
            return self._runner

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = self._session_locks[session_id] = asyncio.Lock()
        return lock

    async def _get_or_create_session(self, session_id: str | None, title_hint: str) -> Any:
        svc = await self.session_service()
        if session_id:
            sess = await svc.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
            if sess is not None:
                return sess
        sid = session_id or storage.new_id("chat")
        title = title_hint.strip().replace("\n", " ")[:60] or "New conversation"
        return await svc.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=sid, state={"title": title, "created_at": storage.now_iso()})

    # ------------------------------------------------------------ chat
    async def chat(self, req: ChatRequest, abort: asyncio.Event) -> AsyncIterator[dict[str, Any]]:
        s = llm_settings.load()
        if not s.configured:
            yield {"event": "error", "data": {"code": "not_configured", "message": "Configure the AI gateway in Settings (URL, key and model) to start chatting."}}
            return
        try:
            runner = await self._ensure_runner()
        except RuntimeError as exc:
            msg = str(exc)
            code = "not_configured" if msg == "not_configured" else "unavailable"
            self.last_error = None if code == "not_configured" else msg
            yield {"event": "error", "data": {"code": code, "message": "Configure the AI gateway in Settings." if code == "not_configured" else msg}}
            return

        from google.adk.agents.run_config import RunConfig, StreamingMode
        from google.genai import types

        session = await self._get_or_create_session(req.session_id, req.message)
        sid = session.id
        yield {"event": "session", "data": {"session_id": sid, "title": (session.state or {}).get("title")}}
        lock = self._lock_for(sid)
        if lock.locked():
            yield {"event": "error", "data": {"code": "busy", "message": "The assistant is still answering the previous message."}}
            return
        async with lock:
            t0 = time.time()
            state_delta = {
                "ui:page": req.ui.page,
                "ui:mode": req.ui.mode,
                "ui:tab": req.ui.tab,
                "ui:selected_dataset_id": req.ui.selected_dataset_id,
                "ui:selected_run_id": req.ui.selected_run_id,
                "ui:selected_alert_id": req.ui.selected_alert_id,
                "ui:drill_store_id": req.ui.drill_store_id,
                "ui:drill_sku_id": req.ui.drill_sku_id,
                "ui:active_model_id": req.ui.active_model_id,
                "ui:selected_schedule_id": req.ui.selected_schedule_id,
                "ui:session_id": sid,
            }
            run_config = RunConfig(streaming_mode=StreamingMode.SSE if s.streaming else StreamingMode.NONE, max_llm_calls=config.ASSISTANT_MAX_LLM_CALLS)
            new_message = types.Content(role="user", parts=[types.Part(text=req.message)])
            streamed: dict[str, Any] = {"__sid__": sid, "__turn__": storage.new_id("turn")}
            try:
                # older google-adk releases have no abort_signal; the loop below still stops on abort
                extra = {"abort_signal": abort} if "abort_signal" in inspect.signature(runner.run_async).parameters else {}
                async with asyncio.timeout(s.timeout_s + 10):
                    async for event in runner.run_async(user_id=USER_ID, session_id=sid, new_message=new_message, state_delta=state_delta, run_config=run_config, **extra):
                        for out in self._map_event(event, streamed):
                            yield out
                        if abort.is_set():
                            break
            except TimeoutError:
                self.last_error = "The gateway took too long to answer."
                yield {"event": "error", "data": {"code": "timeout", "message": self.last_error}}
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self.last_error = self._readable(exc)
                yield {"event": "error", "data": {"code": "llm_error", "message": self.last_error}}
            yield {"event": "done", "data": {"session_id": sid, "elapsed_ms": int((time.time() - t0) * 1000)}}

    @staticmethod
    def _readable(exc: Exception) -> str:
        name = type(exc).__name__
        text = str(exc)
        low = text.lower()
        if "authentication" in name.lower() or "401" in text or "invalid api key" in low:
            return "The gateway rejected the key. Check Settings."
        if "notfound" in name.lower() or "404" in text or "model_not_found" in low or "does not exist" in low:
            return "The gateway does not know this model. Pick another model in Settings."
        if "connection" in name.lower() or "connect" in low:
            return "Cannot reach the gateway. Check the URL, VPN or proxy."
        if "timeout" in name.lower():
            return "The gateway took too long to answer."
        if "ratelimit" in name.lower() or "429" in text:
            return "The gateway is rate-limiting requests; try again in a moment."
        if "tool" in low and ("not support" in low or "unsupported" in low):
            return "This model does not support tool calling through the gateway. Pick a model that does, or switch streaming off in Settings."
        return f"{name}: {text[:300]}"

    def _map_event(self, event: Any, streamed: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        author = getattr(event, "author", None) or "assistant"
        partial = bool(getattr(event, "partial", False))
        actions = getattr(event, "actions", None)
        if actions is not None and getattr(actions, "transfer_to_agent", None):
            out.append({"event": "transfer", "data": {"to": actions.transfer_to_agent, "from": author}})
        seen: set[str] = streamed.setdefault("__calls__", set())  # type: ignore[assignment]
        if not partial:  # streamed partial chunks repeat the same call; only the aggregated event counts
            for fc in event.get_function_calls() or []:
                if fc.name == "transfer_to_agent":
                    continue
                key = f"{fc.id or ''}:{fc.name}:{json.dumps(fc.args or {}, sort_keys=True, default=str)}"
                if key in seen:
                    continue
                seen.add(key)
                args = dict(fc.args or {})
                safe_args = json.loads(json.dumps(args, default=str))
                out.append({"event": "tool_call", "data": {"id": fc.id, "name": fc.name, "args": safe_args, "label": tool_label(fc.name, args), "author": author}})
        for fr in (event.get_function_responses() or []) if not partial else []:
            if fr.name == "transfer_to_agent":
                continue
            resp = fr.response if isinstance(fr.response, dict) else {"result": fr.response}
            if "result" in resp and isinstance(resp.get("result"), dict) and len(resp) == 1:
                resp = resp["result"]
            ok, summary = _summarise_result(fr.name, resp)
            out.append({"event": "tool_result", "data": {"id": fr.id, "name": fr.name, "ok": ok, "summary": summary, "author": author}})
            if fr.name == "propose_job" and isinstance(resp, dict) and resp.get("status") == "proposed":
                p = proposals.get(resp["proposal"]["proposal_id"])
                if p is not None:
                    out.append({"event": "proposal", "data": p.model_dump()})
        content = getattr(event, "content", None)
        text = "".join(part.text for part in (content.parts if content and content.parts else []) if getattr(part, "text", None)) if content else ""
        if text and author != "user":
            if partial:
                streamed[author] = str(streamed.get(author, "")) + text
                out.append({"event": "text", "data": {"delta": text, "author": author}})
            else:
                prev = str(streamed.get(author, ""))
                if prev and text.startswith(prev):
                    delta = text[len(prev) :]
                elif prev and prev.startswith(text):
                    delta = ""
                else:
                    delta = text if not prev else "\n" + text
                if delta:
                    out.append({"event": "text", "data": {"delta": delta, "author": author}})
                streamed[author] = ""
                out.append({"event": "message_end", "data": {"author": author}})
        err = getattr(event, "error_message", None)
        if err:
            out.append({"event": "error", "data": {"code": "agent_error", "message": str(err)[:300]}})
        meta = getattr(event, "usage_metadata", None) if not partial else None
        if meta is not None and author != "user" and (getattr(meta, "prompt_token_count", 0) or getattr(meta, "candidates_token_count", 0)):
            calls = [fc.name for fc in (event.get_function_calls() or []) if fc.name != "transfer_to_agent"]
            rec = usage.record_llm_call(
                session_id=str(streamed.get("__sid__") or ""),
                turn_id=str(streamed.get("__turn__") or ""),
                agent=author,
                model=self._model_id,
                prompt_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
                completion_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
                thoughts_tokens=int(getattr(meta, "thoughts_token_count", 0) or 0),
                cached_tokens=int(getattr(meta, "cached_content_token_count", 0) or 0),
                tool_calls=calls,
                price=self._price,
            )
            out.append({"event": "usage", "data": {"agent": author, "prompt_tokens": rec["prompt_tokens"], "completion_tokens": rec["completion_tokens"], "thoughts_tokens": rec["thoughts_tokens"], "cost_usd": rec["cost_usd"], "session": usage.session_totals(rec["session_id"])}})
        return out

    # ------------------------------------------------------------ history
    async def list_sessions(self) -> list[SessionSummary]:
        svc = await self.session_service()
        resp = await svc.list_sessions(app_name=APP_NAME, user_id=USER_ID)
        out = []
        for sess in getattr(resp, "sessions", []) or []:
            st = sess.state or {}
            out.append(SessionSummary(session_id=sess.id, title=str(st.get("title") or "Conversation"), created_at=st.get("created_at"), updated_at=_ts(getattr(sess, "last_update_time", None)), n_messages=len(getattr(sess, "events", []) or [])))
        out.sort(key=lambda x: x.updated_at or x.created_at or "", reverse=True)
        return out

    async def get_messages(self, session_id: str) -> list[ChatMessage]:
        svc = await self.session_service()
        sess = await svc.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
        if sess is None:
            raise LookupError("Conversation not found.")
        msgs: list[ChatMessage] = []
        current: ChatMessage | None = None
        for ev in sess.events or []:
            if getattr(ev, "partial", False):
                continue
            author = getattr(ev, "author", "") or ""
            content = getattr(ev, "content", None)
            parts = content.parts if content and content.parts else []
            text = "".join(p.text for p in parts if getattr(p, "text", None))
            ts = getattr(ev, "timestamp", None)
            if author == "user":
                role = "system" if text.startswith("[") else "user"
                msgs.append(ChatMessage(id=ev.id, role=role, text=text, timestamp=ts))
                current = None
                continue
            if current is None or current.author != author:
                current = ChatMessage(id=ev.id, role="assistant", author=author, text="", timestamp=ts)
                msgs.append(current)
            for fc in ev.get_function_calls() or []:
                if fc.name == "transfer_to_agent":
                    continue  # hand-overs are shown by the author tag, not as a tool chip (same as the live stream)
                current.tools.append(ToolActivity(id=fc.id, name=fc.name, label=tool_label(fc.name, dict(fc.args or {})), author=author))
            for fr in ev.get_function_responses() or []:
                if fr.name == "transfer_to_agent":
                    continue
                resp = fr.response if isinstance(fr.response, dict) else {}
                if "result" in resp and isinstance(resp.get("result"), dict) and len(resp) == 1:
                    resp = resp["result"]
                ok, summary = _summarise_result(fr.name, resp)
                for t in current.tools:
                    if t.id == fr.id or (t.name == fr.name and t.ok is None):
                        t.ok, t.summary = ok, summary
                        break
                if fr.name == "propose_job" and resp.get("status") == "proposed":
                    p = proposals.get(resp["proposal"]["proposal_id"])
                    if p is not None:
                        current.proposals.append(p.model_dump())
            if text:
                current.text = (current.text + ("\n" if current.text else "") + text) if current.text != text else current.text
        # A root agent that only handed over leaves nothing to show.
        return [m for m in msgs if m.role != "assistant" or m.text or m.tools or m.proposals]

    async def delete_session(self, session_id: str) -> None:
        svc = await self.session_service()
        await svc.delete_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
        self._session_locks.pop(session_id, None)


def _ts(v: Any) -> str | None:
    if v is None:
        return None
    try:
        from datetime import datetime

        return datetime.fromtimestamp(float(v)).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError):
        return None


engine = AssistantEngine()
