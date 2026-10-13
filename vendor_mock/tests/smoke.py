"""Contract smoke test for the demo vendor: start it on a free port with a tiny estate and talk to it over MCP.

    python vendor_mock/tests/smoke.py
Checks paging returns every visible row exactly once, cursors are stable, the clock reveals new days, the task
lifecycle (create, idempotent repeat, store-side update, read back) and bearer-token auth.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "smoke-token"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {str(detail)[:400]}"))
    if not ok:
        raise SystemExit(1)


def http(method: str, url: str, data: dict | None = None) -> tuple[int, str]:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


async def call(base: str, name: str, args: dict, token: str | None = TOKEN) -> dict:
    from mcp import ClientSession

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client  # mcp >= 1.2x and 2.x

        http = create_mcp_http_client(headers=headers)
        cm = streamable_http_client(base + "/mcp/", http_client=http)
    except ImportError:  # older 1.x
        from mcp.client.streamable_http import streamablehttp_client

        http = None
        cm = streamablehttp_client(base + "/mcp/", headers=headers)
    try:
        async with cm as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                await s.initialize()
                res = await s.call_tool(name, args)
                return json.loads(res.content[0].text)
    finally:
        if http is not None:
            await http.aclose()


def mcp(base: str, name: str, **args) -> dict:
    return asyncio.run(call(base, name, args))


def start_server(data_dir: str, port: int) -> subprocess.Popen:
    env = dict(os.environ, VENDOR_MOCK_DATA_DIR=data_dir, VENDOR_MOCK_STORES="10", VENDOR_MOCK_SKUS="60", VENDOR_MOCK_HISTORY_DAYS="90",
               VENDOR_MOCK_FUTURE_DAYS="20", VENDOR_MOCK_TOKEN=TOKEN, VENDOR_MOCK_PUBLIC_URL=f"http://127.0.0.1:{port}", PYTHONUTF8="1")
    return subprocess.Popen([sys.executable, "-m", "uvicorn", "vendor_mock.app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env)


def wait_ready(base: str, timeout: float = 120) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s, body = http("GET", base + "/health")
            h = json.loads(body)
            if s == 200 and h.get("data") == "ready":
                return h
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise SystemExit("vendor mock did not become ready")


def main() -> None:
    data_dir = tempfile.mkdtemp(prefix="vendor_smoke_")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start_server(data_dir, port)
    try:
        h = wait_ready(base)
        print("     ready:", h)
        # auth
        try:
            asyncio.run(call(base, "get_capabilities", {}, token=None))
            check("mcp refuses a missing token", False, "call succeeded")
        except Exception:  # noqa: BLE001
            check("mcp refuses a missing token", True)
        cap = mcp(base, "get_capabilities")
        check("capabilities", cap["contract"] == "sentinel-inventory-connector" and cap["status"] == "ready" and cap["counts"]["stores"] == 10, cap)
        first, last = cap["data_range"]["first_date"], cap["data_range"]["last_date"]
        # paging: every row exactly once
        keys, cursor, pages = set(), None, 0
        total_rows = 0
        while True:
            pg = mcp(base, "get_daily_movements", since=first, cursor=cursor, page_size=7000)
            pages += 1
            d = pg["data"]
            n = pg["row_count"]
            total_rows += n
            if n:
                dates = [d["date"]["dict"][i] for i in d["date"]["idx"]]
                st = [d["store_id"]["dict"][i] for i in d["store_id"]["idx"]]
                sk = [d["sku_id"]["dict"][i] for i in d["sku_id"]["idx"]]
                keys.update(zip(dates, st, sk))
                check(f"page {pages} columns line up", all(len(d[c]) == n for c in pg["columns"][3:]), {c: len(d[c]) for c in pg["columns"]})
            cursor = pg["next_cursor"]
            if not cursor:
                break
        expected = 10 * 60 * ((__import__("datetime").date.fromisoformat(last) - __import__("datetime").date.fromisoformat(first)).days + 1)
        check("paging returns every visible row exactly once", total_rows == len(keys) == expected, (total_rows, len(keys), expected))
        check("no row after the last closed day", max(k[0] for k in keys) == last, max(k[0] for k in keys))
        # clock
        s, body = http("POST", base + "/api/advance?days=1", {})
        adv = json.loads(body)
        check("advance one business day", s == 200 and adv["advanced"] == 1, body)
        new = mcp(base, "get_daily_movements", since=last)
        new_dates = set(new["data"]["date"]["dict"])
        check("advancing reveals the next day", len(new_dates) == 2 and new["row_count"] == 2 * 600, (new_dates, new["row_count"]))
        flags = mcp(base, "get_lp_flags", since=first)
        check("lp flags", isinstance(flags["items"], list) and all(f["reported_on"] >= f["date"] for f in flags["items"]), flags["items"][:2])
        ak = mcp(base, "get_answer_key", since=first, page_size=100000)
        check("answer key (demo only)", ak["row_count"] > 0 and ak["demo_only"], ak["row_count"])
        pos = mcp(base, "get_stock_position", store_id="S001", sku_id="K00001", days=5)
        check("stock position", pos["on_hand"] is not None and len(pos["last_days"]) == 5, pos)
        bad = mcp(base, "get_stock_position", store_id="S999", sku_id="K00001")
        check("unknown store is a vendor error", bad.get("error", {}).get("code") == "not_found", bad)
        # tasks
        t1 = mcp(base, "create_task", type="recount", store_id="S001", sku_id="K00001", title="Recount K00001", priority="high", idempotency_key="S001|K00001|x:recount", source_alert_id="A1")
        t2 = mcp(base, "create_task", type="recount", store_id="S001", sku_id="K00001", title="Recount K00001", priority="high", idempotency_key="S001|K00001|x:recount")
        check("create task", t1["created"] and t1["status"] == "open", t1)
        check("idempotent repeat returns the same task", (not t2["created"]) and t2["task_id"] == t1["task_id"], t2)
        bad = mcp(base, "create_task", type="teleport", store_id="S001", title="x")
        check("bad task type rejected", bad.get("error", {}).get("code") == "bad_request", bad)
        s, _ = http("POST", f"{base}/tasks/{t1['task_id']}", {"status": "done", "outcome": "count_corrected", "outcome_units": "4", "note": "found in stockroom"})
        check("store-side update via the back-office form", s in (200, 303), s)
        got = mcp(base, "get_task", task_id=t1["task_id"])
        check("outcome read back", got["status"] == "done" and got["outcome"] == "count_corrected" and got["outcome_units"] == 4 and len(got["events"]) >= 2, got)
        lst = mcp(base, "list_tasks", status="done")
        check("list tasks by status", any(t["task_id"] == t1["task_id"] for t in lst["items"]), lst)
        for path in ("/", "/stores", "/skus", "/ledger?store=S001&sku=K00001", "/lp-flags", "/tasks", f"/tasks/{t1['task_id']}", "/answer-key"):
            s, body = http("GET", base + path)
            check(f"page {path}", s == 200 and "<html" in body, s)
        print("ALL PASS")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
