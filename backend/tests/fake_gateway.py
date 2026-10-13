"""A tiny OpenAI-compatible 'LiteLLM gateway' for offline tests of the assistant.

    python backend/tests/fake_gateway.py            # serves on http://127.0.0.1:8111, key "test-key"

Scripted brain: it does not understand language, it pattern-matches the last user message to decide
whether to call a tool, and when it sees a tool result it answers with a sentence quoting one field.
Supports streaming (SSE chunks) and non-streaming responses, `GET /v1/models`, and Bearer auth.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

API_KEY = "test-key"
MODEL = "fake-tool-model"
app = FastAPI(title="fake gateway")


def _auth(authorization: str | None) -> None:
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(401, {"error": {"message": "invalid api key"}})


@app.get("/v1/models")
def models(authorization: str | None = Header(None)) -> dict[str, Any]:
    _auth(authorization)
    return {"object": "list", "data": [{"id": MODEL, "object": "model"}, {"id": "fake-plain-model", "object": "model"}]}


def _last(messages: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    for m in reversed(messages):
        if m.get("role") == role:
            return m
    return None


def _text(m: dict[str, Any] | None) -> str:
    if not m:
        return ""
    c = m.get("content")
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return str(c or "")


def decide(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Returns (tool_name, tool_args, text)."""
    names = {t.get("function", {}).get("name") for t in tools or []}
    last = messages[-1] if messages else {}
    if last.get("role") == "tool":
        try:
            payload = json.loads(_text(last))
        except ValueError:
            payload = {}
        if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], dict):
            payload = payload["result"]
        if isinstance(payload, dict):
            if "datasets" in payload:
                return None, None, f"You have {payload.get('count', len(payload['datasets']))} datasets loaded. The latest is '{payload['datasets'][0]['name']}' with {payload['datasets'][0]['rows']:,} store-SKU-days." if payload.get("datasets") else "You have no datasets yet."
            if "proposal" in payload:
                p = payload["proposal"]
                return None, None, f"I have prepared: {p['title']}. {p['summary']} Press Confirm to start it."
            if "reasons" in payload and "alert_id" in payload:
                return None, None, f"Alert {payload['alert_id']} ({payload.get('likely_type')}, {payload.get('severity')}) was flagged because: {payload['reasons'][0] if payload['reasons'] else 'several signals'}. About £{payload.get('value_at_risk_gbp', 0):,.0f} is at risk."
            if "expected_recovered_gbp" in payload:
                return None, None, f"With {payload.get('hours')} hours you can work {payload.get('alerts_selected')} alerts and expect to recover about £{payload['expected_recovered_gbp']:,.0f} (estimate)."
            if "alerts" in payload and "total_matching" in payload:
                return None, None, f"There are {payload['total_matching']} matching alerts; the top one is {payload['alerts'][0]['alert_id'] if payload['alerts'] else 'none'}."
            if "jobs" in payload:
                return None, None, f"There are {payload.get('n_active', 0)} active jobs."
            if "schedules" in payload:
                return None, None, f"You have {payload.get('count', 0)} schedule(s)" + (f"; '{payload['schedules'][0]['name']}' runs next at {payload['schedules'][0]['next_run_at_utc']} UTC." if payload.get("schedules") else ".")
            if "sop" in payload and "steps" in payload:
                return None, None, f"Follow SOP {payload['sop']['id']} (v{payload['sop']['version']}): first, {payload['steps'][0]['text'] if payload['steps'] else 'see the SOP'}"
            if payload.get("live") and "on_hand" in payload:
                return None, None, f"Live from the vendor: {payload['on_hand']} on hand as of {payload.get('as_of')}."
            if "connectors" in payload:
                return None, None, f"You have {payload.get('count', 0)} vendor connector(s)."
            if payload.get("status") == "error":
                return None, None, f"That did not work: {payload.get('error_message')}"
        return None, None, "Done. " + json.dumps(payload)[:160]
    # Like a real model, consider the conversation: the latest genuine user question (ADK inserts
    # "For context: ..." user-role notes after a hand-over) plus everything the user said before.
    user_msgs = [_text(m) for m in messages if m.get("role") == "user"]
    genuine = [u for u in user_msgs if not u.lower().startswith("for context")]
    user = ((genuine[-1] if genuine else _text(_last(messages, "user"))) + " " + " ".join(user_msgs)).lower()
    if "reply with exactly" in user or user.strip() == "reply ok":
        return None, None, "OK"
    # (tool, args, owning specialist) — like a real model, transfer when the current agent lacks the tool.
    want: tuple[str, dict[str, Any], str | None] | None = None
    m = re.search(r"\b(a\d{6})\b", user)
    cur = (genuine[-1] if genuine else "").lower()  # operations routes look at the latest question only
    stock = re.search(r"stock of (k\d{5}) at (s\d{3})", cur)
    if "sop" in cur or "procedure" in cur:
        want = ("get_sop", {"likely_type": "counting_error"}, "ops_coordinator")
    elif stock:
        want = ("vendor_lookup", {"store_id": stock.group(2).upper(), "sku_id": stock.group(1).upper()}, "data_analyst")
    elif "schedule" in cur:
        want = ("list_schedules", {}, "ops_coordinator")
    elif "connector" in cur:
        want = ("list_connectors", {}, "ops_coordinator")
    elif m:
        want = ("explain_alert", {"alert_id": m.group(1).upper()}, "alert_investigator")
    elif "hours" in user or "plan" in user:
        want = ("investigation_plan", {"hours": 120}, "lp_planner")
    elif "alert" in user:
        want = ("list_alerts", {"severity": "critical", "limit": 5}, "alert_investigator")
    elif "detect" in user:
        want = ("propose_job", {"kind": "detect", "params": {}}, "alert_investigator")
    elif "train" in user:
        want = ("propose_job", {"kind": "train", "params": {"quick": True}}, "model_analyst")
    elif "dataset" in user:
        want = ("list_datasets", {}, "data_analyst")
    elif "job" in user or "[confirmed" in user or "[job" in user:
        want = ("job_status", {}, None)
    if want:
        name, args, owner = want
        if name in names:
            return name, args, None
        if owner and "transfer_to_agent" in names:
            return "transfer_to_agent", {"agent_name": owner}, None
    return None, None, f"I heard: {user[:60]}. Ask me about datasets, alerts, an alert id, or investigator hours."


def _chunk(cid: str, delta: dict[str, Any], finish: str | None = None) -> str:
    return "data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}) + "\n\n"


@app.post("/v1/chat/completions")
async def chat(request: Request, authorization: str | None = Header(None)):
    _auth(authorization)
    body = await request.json()
    messages = body.get("messages", [])
    tool_name, tool_args, text = decide(messages, body.get("tools") or [])
    cid = "chatcmpl-" + uuid.uuid4().hex[:12]
    call_id = "call_" + uuid.uuid4().hex[:8]
    if not body.get("stream"):
        if tool_name:
            msg = {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(tool_args or {})}}]}
            finish = "tool_calls"
        else:
            msg = {"role": "assistant", "content": text}
            finish = "stop"
        return JSONResponse({"id": cid, "object": "chat.completion", "created": int(time.time()), "model": MODEL, "choices": [{"index": 0, "message": msg, "finish_reason": finish}], "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})

    def stream():
        yield _chunk(cid, {"role": "assistant", "content": ""})
        if tool_name:
            yield _chunk(cid, {"tool_calls": [{"index": 0, "id": call_id, "type": "function", "function": {"name": tool_name, "arguments": ""}}]})
            args = json.dumps(tool_args or {})
            for i in range(0, len(args), 12):
                yield _chunk(cid, {"tool_calls": [{"index": 0, "function": {"arguments": args[i : i + 12]}}]})
            yield _chunk(cid, {}, "tool_calls")
        else:
            words = (text or "").split(" ")
            for i, w in enumerate(words):
                yield _chunk(cid, {"content": (w if i == 0 else " " + w)})
                time.sleep(0.01)
            yield _chunk(cid, {}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def serve_in_thread(port: int = 8111) -> threading.Thread:
    import uvicorn

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    t = threading.Thread(target=server.run, daemon=True, name="fake-gateway")
    t.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return t


if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8111
    print(f"fake gateway on http://127.0.0.1:{port}  key={API_KEY} model={MODEL}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
