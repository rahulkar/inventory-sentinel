"""Offline end-to-end check of the assistant: settings, streaming chat with tool calls, proposals, sessions, MCP.

    python backend/tests/assistant_smoke.py [--base http://127.0.0.1:8000] [--gateway URL --key KEY --model ID]

Without --gateway it starts the fake OpenAI-compatible gateway on 127.0.0.1:8111 in a thread.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:8000")
ap.add_argument("--gateway", default=None)
ap.add_argument("--key", default=None)
ap.add_argument("--model", default=None)
args = ap.parse_args()
B = args.base


def call(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            return r.status, (json.loads(payload) if "json" in r.headers.get("Content-Type", "") else payload)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def check(label, cond, detail=""):
    print(("PASS" if cond else "FAIL"), label, "" if cond else detail)
    if not cond:
        sys.exit(1)


def chat(message, session_id=None, ui=None, timeout=180):
    """POST the chat and parse the SSE stream into a list of (event, data)."""
    body = json.dumps({"session_id": session_id, "message": message, "ui": ui or {"page": "overview", "selected_dataset_id": None, "selected_run_id": None, "active_model_id": None}}).encode()
    req = urllib.request.Request(B + "/api/assistant/chat", data=body, method="POST", headers={"Content-Type": "application/json"})
    events = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        buf = b""
        while True:
            chunk = r.read(1)
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf:
                frame, buf = buf.split(b"\n\n", 1)
                text = frame.decode("utf-8", errors="replace")
                if text.startswith(":"):
                    continue
                ev, data = "message", ""
                for line in text.split("\n"):
                    if line.startswith("event:"):
                        ev = line[6:].strip()
                    elif line.startswith("data:"):
                        data += line[5:].strip()
                events.append((ev, json.loads(data) if data else {}))
    return events


# ------------------------------------------------------------------ gateway
if args.gateway:
    gw_url, gw_key, gw_model = args.gateway, args.key or "", args.model or ""
else:
    from fake_gateway import API_KEY, MODEL, serve_in_thread

    serve_in_thread(8111)
    gw_url, gw_key, gw_model = "http://127.0.0.1:8111", API_KEY, MODEL
    print("     fake gateway up on", gw_url)

s, st = call("GET", "/api/assistant/status")
check("assistant status", s == 200, st)
print("     available:", st["available"], st.get("reason") or "", "| versions:", st["versions"])

# not configured -> single error event
s, _ = call("PUT", "/api/settings/llm", {"base_url": "", "model": ""})
ev = chat("hello")
check("not configured -> error event", ev and ev[0][0] == "error" and ev[0][1].get("code") == "not_configured", ev[:2])

# ------------------------------------------------------------------ settings
s, probe = call("POST", "/api/settings/llm/test", {"base_url": gw_url, "api_key": gw_key, "model": None})
check("test: list models", s == 200 and probe["ok"] and probe["models"], probe)
model = gw_model or probe["models"][0]
s, probe = call("POST", "/api/settings/llm/test", {"base_url": gw_url, "api_key": gw_key, "model": model})
check("test: chat probe", s == 200 and probe["chat_ok"], probe)
print(f"     reply={probe['reply']!r} latency={probe['latency_ms']}ms")
s, saved = call("PUT", "/api/settings/llm", {"base_url": gw_url + "/v1/", "api_key": gw_key, "model": model, "temperature": 0.1, "streaming": True, "agent_mode": "team"})
check("settings saved (url normalised, key masked)", s == 200 and saved["base_url"] == gw_url and saved["has_key"] and "•" in saved["api_key_masked"] and saved["configured"], saved)
s, got = call("GET", "/api/settings/llm")
check("settings GET never returns the key", "api_key" not in got and got["api_key_masked"].endswith(gw_key[-4:]), got)
s, saved2 = call("PUT", "/api/settings/llm", {"api_key": "", "temperature": 0.2})
check("blank key keeps stored key", saved2["has_key"], saved2)

# ------------------------------------------------------------------ chat with tools
t0 = time.time()
ev = chat("What datasets do I have?")
kinds = [e for e, _ in ev]
print(f"     events: {kinds} ({time.time()-t0:.1f}s)")
check("chat: session + done", "session" in kinds and kinds[-1] == "done", kinds)
called = [d["name"] for e, d in ev if e == "tool_call"]
if args.gateway:
    # A real model may answer from the context pack, app_state or list_datasets; only the fake gateway is scripted.
    # It may even answer straight from the context pack (which already lists datasets) without any tool.
    print("     tools called:", called or "none (answered from context pack)", "| hand-over:", "transfer" in kinds)
else:
    check("chat: tool call + result", "list_datasets" in called and "tool_result" in kinds, {"called": called, "kinds": kinds})
    check("chat: specialist hand-over", "transfer" in kinds, kinds)
text = "".join(d["delta"] for e, d in ev if e == "text")
check("chat: answer mentions datasets", "dataset" in text.lower(), text[:200])
sid = next(d["session_id"] for e, d in ev if e == "session")
errors = [d for e, d in ev if e == "error"]
check("chat: no errors", not errors, errors)
print("     answer:", text[:140].replace("\n", " "))

ev = chat("Please train the recommended models", session_id=sid, ui={"page": "train", "selected_dataset_id": None, "selected_run_id": None, "active_model_id": None})
props = [d for e, d in ev if e == "proposal"]
check("chat: proposal event", bool(props), [e for e, _ in ev])
p = props[0]
print("     proposal:", p["title"], "| status", p["status"], "| est", p["estimate_seconds"])
s, listed = call("GET", f"/api/assistant/proposals?session_id={sid}")
check("proposals listed for session", s == 200 and any(x["proposal_id"] == p["proposal_id"] for x in listed), listed)
s, out = call("POST", f"/api/assistant/proposals/{p['proposal_id']}/confirm")
check("confirm starts a job", s == 200 and out["proposal"]["status"] == "confirmed" and out["job"], out)
job_id = out["job"]["job_id"]
s, again = call("POST", f"/api/assistant/proposals/{p['proposal_id']}/confirm")
check("second confirm refused", s == 409, again)
while True:
    s, j = call("GET", f"/api/jobs/{job_id}")
    if j["status"] in ("done", "failed", "cancelled"):
        break
    time.sleep(1)
check("confirmed job finished", j["status"] == "done", j.get("error"))
ev = chat(f"[confirmed {p['proposal_id']}] Job {job_id} started. What is its status?", session_id=sid)
check("follow-up turn answered", any(e == "text" for e, _ in ev) and [e for e, _ in ev][-1] == "done", [e for e, _ in ev])

# ------------------------------------------------------------------ sessions persist across an engine rebuild
s, _ = call("PUT", "/api/settings/llm", {"temperature": 0.3})  # invalidates the runner
s, sessions = call("GET", "/api/assistant/sessions")
check("session listed", s == 200 and any(x["session_id"] == sid for x in sessions), sessions)
s, msgs = call("GET", f"/api/assistant/sessions/{sid}/messages")
roles = [m["role"] for m in msgs]
check("transcript rebuilt", s == 200 and "user" in roles and "assistant" in roles and any(m["tools"] for m in msgs), roles)
check("transcript has the proposal", any(m["proposals"] for m in msgs), [len(m["proposals"]) for m in msgs])
print("     messages:", len(msgs), "roles:", roles)

# ------------------------------------------------------------------ MCP
async def mcp_check():
    from mcp import ClientSession

    try:
        from mcp.client.streamable_http import streamable_http_client as _client  # mcp >= 2
    except ImportError:
        from mcp.client.streamable_http import streamablehttp_client as _client  # mcp 1.x

    async with _client(B + "/mcp/") as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            res = await session.call_tool("list_datasets", {})
            payload = json.loads(res.content[0].text) if res.content and getattr(res.content[0], "text", None) else {}
            docs = await session.call_tool("search_docs", {"query": "how is ROI calculated"})
            return names, payload, docs

names, payload, docs = asyncio.run(mcp_check())
check("mcp: tools listed", len(names) >= 24, names)
check("mcp: list_datasets works", payload.get("status") == "ok", payload)
print(f"     mcp tools: {len(names)}; datasets via mcp: {payload.get('count')}")

s, _ = call("DELETE", f"/api/assistant/sessions/{sid}")
check("session deleted", s == 200, _)
print("ALL PASS")
