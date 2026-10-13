"""Server-rendered back-office pages for the demo vendor (no build step): what a store-operations user would see."""
from __future__ import annotations

import html
from typing import Any, Iterable
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from vendor_mock import db, seed, service, settings

router = APIRouter(include_in_schema=False)
e = html.escape
PAGE = 50

CSS = """
:root{--bg:#f3f4f2;--panel:#fff;--ink:#1d2421;--muted:#5d6763;--line:#d9ddd9;--brand:#0f6e5c;--brand-ink:#fff;--warn:#9a5b00;--bad:#a12a2a;--ok:#1d6b35;--chip:#e7ece9}
@media (prefers-color-scheme:dark){:root{--bg:#141816;--panel:#1c211f;--ink:#e3e8e5;--muted:#9aa5a0;--line:#2e3532;--brand:#3fb59b;--brand-ink:#0d1210;--warn:#e0a54a;--bad:#e07272;--ok:#6fcf8c;--chip:#26302c}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink)}
header{background:var(--brand);color:var(--brand-ink);padding:10px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header b{font-size:16px}header .badge{background:rgba(0,0,0,.18);padding:2px 8px;border-radius:10px;font-size:12px}
nav{display:flex;gap:4px;flex-wrap:wrap;padding:6px 12px;background:var(--panel);border-bottom:1px solid var(--line)}
nav a{color:var(--ink);text-decoration:none;padding:6px 10px;border-radius:6px}nav a.on,nav a:hover{background:var(--chip)}
main{max-width:1200px;margin:0 auto;padding:16px}h1{font-size:20px;margin:4px 0 12px}h2{font-size:15px;margin:18px 0 8px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.kpi b{display:block;font-size:22px}.kpi span{color:var(--muted);font-size:12px}
.tbl{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:12px}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
a{color:var(--brand)}.muted{color:var(--muted)}.chip{display:inline-block;background:var(--chip);border-radius:10px;padding:1px 8px;font-size:12px}
.chip.open{color:var(--warn)}.chip.done{color:var(--ok)}.chip.rejected{color:var(--bad)}.chip.urgent,.chip.high{color:var(--bad)}
form.inline{display:inline}button,select,input,textarea{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:6px 10px}
button{background:var(--brand);color:var(--brand-ink);border-color:var(--brand);cursor:pointer}button.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.pager{display:flex;gap:12px;margin-top:10px}.bad{color:var(--bad)}.warn{color:var(--warn)}
label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted)}textarea{width:100%;min-height:70px}
code{background:var(--chip);padding:1px 5px;border-radius:4px}
@media (max-width:600px){main{padding:12px}header{padding:10px 12px}}
"""

NAV = [("/", "Dashboard"), ("/stores", "Stores"), ("/skus", "Products"), ("/ledger", "Stock ledger"), ("/lp-flags", "Loss prevention"), ("/tasks", "Tasks from Sentinel"), ("/answer-key", "Demo answer key")]


def render(title: str, body: str, active: str = "/") -> HTMLResponse:
    st = db.get_meta("status", "empty")
    clock = ""
    if st == "ready":
        c = service.clock()
        clock = f'<span class="badge">Business date {e(c["business_date"])}</span>'
    nav = "".join(f'<a href="{h}" class="{"on" if h == active else ""}">{e(t)}</a>' for h, t in NAV)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · {e(settings.VENDOR_NAME)}</title><style>{CSS}</style></head><body>
<header><b>{e(settings.VENDOR_NAME)}</b><span>Store operations back-office</span><span class="badge">SIMULATED DEMO DATA</span>{clock}</header>
<nav>{nav}</nav><main>{body}</main></body></html>"""
    return HTMLResponse(doc)


def table(headers: list[str], rows: Iterable[list[Any]], numeric: set[int] | None = None) -> str:
    numeric = numeric or set()
    th = "".join(f'<th class="{"n" if i in numeric else ""}">{e(h)}</th>' for i, h in enumerate(headers))
    body = []
    for r in rows:
        tds = []
        for i, v in enumerate(r):
            cell = v if isinstance(v, Raw) else e("" if v is None else str(v))
            tds.append(f'<td class="{"n" if i in numeric else ""}">{cell}</td>')
        body.append(f"<tr>{''.join(tds)}</tr>")
    if not body:
        body.append(f'<tr><td colspan="{len(headers)}" class="muted">Nothing to show.</td></tr>')
    return f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


class Raw(str):
    """Pre-escaped HTML for a table cell."""


def chip(text: str, cls: str = "") -> Raw:
    return Raw(f'<span class="chip {e(cls)}">{e(text)}</span>')


def link(href: str, text: str) -> Raw:
    return Raw(f'<a href="{e(href)}">{e(text)}</a>')


def pager(base: str, params: dict[str, Any], page_no: int, has_next: bool) -> str:
    parts = []
    if page_no > 1:
        parts.append(f'<a href="{base}?{urlencode({**params, "page": page_no - 1})}">← Previous</a>')
    parts.append(f'<span class="muted">Page {page_no}</span>')
    if has_next:
        parts.append(f'<a href="{base}?{urlencode({**params, "page": page_no + 1})}">Next →</a>')
    return f'<div class="pager">{"".join(parts)}</div>'


def _not_ready() -> HTMLResponse | None:
    st = seed.status()
    if st["status"] == "ready":
        return None
    msg = "Loading the simulated estate" if st["status"] == "seeding" else f"Data is not available ({st['status']})"
    body = f'<div class="card"><h1>{e(msg)}…</h1><p>{e(st.get("message") or "")} ({st["progress"]:.0%})</p><p class="muted">This page refreshes every few seconds.</p></div><script>setTimeout(()=>location.reload(),3000)</script>'
    return render("Loading", body)


# ---------------------------------------------------------------- pages
@router.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    if (nr := _not_ready()) is not None:
        return nr
    c = db.conn()
    clk = service.clock()
    n_st = c.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
    n_sk = c.execute("SELECT COUNT(*) FROM skus").fetchone()[0]
    vis = service.visible_through()
    n_rows = c.execute("SELECT COUNT(*) FROM daily WHERE day <= ?", (vis,)).fetchone()[0]
    n_flags = c.execute("SELECT COUNT(*) FROM lp_flags WHERE reported_day <= ?", (vis,)).fetchone()[0]
    by_status = dict(c.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall())
    recent = c.execute("SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 8").fetchall()
    token_note = "a bearer token (VENDOR_MOCK_TOKEN)" if settings.TOKEN else "no token (set VENDOR_MOCK_TOKEN to require one)"
    body = f"""
<h1>Dashboard</h1>
<div class="grid">
  <div class="card kpi"><b>{e(clk['business_date'])}</b><span>Business date · data closed through {e(clk['data_through'] or '—')}</span></div>
  <div class="card kpi"><b>{n_st:,} / {n_sk:,}</b><span>Stores / products</span></div>
  <div class="card kpi"><b>{n_rows:,}</b><span>Daily stock rows since {e(clk['first_date'])}</span></div>
  <div class="card kpi"><b>{n_flags:,}</b><span>Loss-prevention flags reported</span></div>
  <div class="card kpi"><b>{by_status.get('open', 0) + by_status.get('acknowledged', 0) + by_status.get('in_progress', 0)}</b><span>Open tasks from Sentinel ({by_status.get('done', 0)} done)</span></div>
</div>
<div class="card">
  <h2 style="margin-top:0">Business clock</h2>
  <p class="muted">The clock follows the calendar: each night the day's trading closes and becomes available to Sentinel. Fast-forward to
  simulate the next days now ({clk['days_left']} simulated days left).</p>
  <div class="row">
    <form class="inline" method="post" action="/admin/advance"><input type="hidden" name="days" value="1"><button>Close today's trading (+1 day)</button></form>
    <form class="inline" method="post" action="/admin/advance"><input type="hidden" name="days" value="7"><button class="ghost">+7 days</button></form>
  </div>
</div>
<div class="card">
  <h2 style="margin-top:0">Recent tasks from Sentinel</h2>
  {table(["Task", "Type", "Store", "SKU", "Priority", "Status", "Updated"], ([link(f"/tasks/{r['task_id']}", r['task_id']), r['type'], r['store_id'], r['sku_id'] or '', chip(r['priority'], r['priority']), chip(r['status'], r['status']), r['updated_at']] for r in recent))}
</div>
<div class="card">
  <h2 style="margin-top:0">Connector</h2>
  <p>Sentinel connects over MCP at <code>{e(settings.PUBLIC_URL)}/mcp/</code> with {e(token_note)}, using the Sentinel Inventory Connector contract v1.</p>
  <form method="post" action="/admin/reseed" onsubmit="return confirm('Throw away all demo data and tasks and simulate a fresh estate?')"><button class="ghost">Reset demo data…</button></form>
</div>"""
    return render("Dashboard", body, "/")


@router.get("/stores", response_class=HTMLResponse)
def stores() -> HTMLResponse:
    if (nr := _not_ready()) is not None:
        return nr
    rows = db.conn().execute("SELECT * FROM stores ORDER BY store_code").fetchall()
    body = "<h1>Stores</h1><div class='card'>" + table(
        ["Store", "Name", "Region", "Format", "Size", "Team", "Hours"],
        ([r["store_id"], r["store_name"], r["region"], r["format"], r["size_band"], r["warehouse_team"], f"{r['opens_at']}–{r['closes_at']}"] for r in rows),
    ) + "</div>"
    return render("Stores", body, "/stores")


@router.get("/skus", response_class=HTMLResponse)
def skus(q: str = "", page: int = 1) -> HTMLResponse:
    if (nr := _not_ready()) is not None:
        return nr
    p = max(1, page)
    like = f"%{q}%"
    rows = db.conn().execute(
        "SELECT * FROM skus WHERE sku_id LIKE ? OR sku_name LIKE ? OR category LIKE ? ORDER BY sku_code LIMIT ? OFFSET ?", (like, like, like, PAGE + 1, (p - 1) * PAGE)
    ).fetchall()
    form = f'<form class="row" method="get"><input name="q" value="{e(q)}" placeholder="Search SKU, name or category"><button>Search</button></form>'
    body = "<h1>Products</h1><div class='card'>" + form + table(
        ["SKU", "Name", "Category", "Unit cost", "Price", "High theft risk", "Tagged"],
        ([r["sku_id"], r["sku_name"], r["category"], f"£{r['unit_cost']:.2f}", f"£{r['unit_price']:.2f}", "yes" if r["high_theft_risk"] else "", "yes" if r["security_tagged"] else ""] for r in rows[:PAGE]),
        {3, 4},
    ) + pager("/skus", {"q": q}, p, len(rows) > PAGE) + "</div>"
    return render("Products", body, "/skus")


@router.get("/ledger", response_class=HTMLResponse)
def ledger(store: str = "", sku: str = "", days: int = 30) -> HTMLResponse:
    if (nr := _not_ready()) is not None:
        return nr
    c = db.conn()
    store = store or c.execute("SELECT store_id FROM stores ORDER BY store_code LIMIT 1").fetchone()[0]
    sku = sku or c.execute("SELECT sku_id FROM skus ORDER BY sku_code LIMIT 1").fetchone()[0]
    days = max(7, min(int(days), 120))
    form = f"""<form class="row" method="get"><label>Store<input name="store" value="{e(store)}"></label><label>SKU<input name="sku" value="{e(sku)}"></label>
<label>Days<input name="days" type="number" min="7" max="120" value="{days}"></label><button>Show</button></form>"""
    try:
        pos = service.stock_position(store, sku, 1)
        st = c.execute("SELECT store_code FROM stores WHERE store_id = ?", (store,)).fetchone()[0]
        sk = c.execute("SELECT sku_code FROM skus WHERE sku_id = ?", (sku,)).fetchone()[0]
        vis = service.visible_through()
        rows = c.execute("SELECT * FROM daily WHERE store_code = ? AND sku_code = ? AND day <= ? AND day > ? ORDER BY day DESC", (st, sk, vis, vis - days)).fetchall()
        head = f"<p><b>{e(pos['sku']['sku_name'])}</b> ({e(sku)}, {e(pos['sku']['category'])}) at <b>{e(pos['store']['store_name'])}</b> · on hand {pos['on_hand']}</p>"
        tbl = table(
            ["Date", "Opening", "Received", "Sold", "Returns", "Transfers in/out", "Adjust.", "Expected", "Counted", "Variance", "Promo"],
            ([service.day_str(r["day"]), r["opening_stock"], r["received_units"], r["sold_units"], r["returned_units"], f"{r['transfer_in_units']}/{r['transfer_out_units']}",
              r["adjustment_units"], r["expected_closing"], r["counted_closing"], r["expected_closing"] - r["counted_closing"], "yes" if r["on_promo"] else ""] for r in rows),
            {1, 2, 3, 4, 6, 7, 8, 9},
        )
    except service.VendorError as exc:
        head, tbl = f'<p class="bad">{e(exc.message)}</p>', ""
    body = "<h1>Stock ledger</h1><div class='card'>" + form + head + tbl + "</div>"
    return render("Stock ledger", body, "/ledger")


@router.get("/lp-flags", response_class=HTMLResponse)
def lp_flags(page: int = 1) -> HTMLResponse:
    if (nr := _not_ready()) is not None:
        return nr
    p = max(1, page)
    vis = service.visible_through()
    rows = db.conn().execute(
        "SELECT f.*, s.store_id, k.sku_id FROM lp_flags f JOIN stores s USING(store_code) JOIN skus k USING(sku_code) WHERE reported_day <= ? ORDER BY reported_day DESC, flag_id LIMIT ? OFFSET ?",
        (vis, PAGE + 1, (p - 1) * PAGE),
    ).fetchall()
    body = "<h1>Loss-prevention flags</h1><div class='card'><p class='muted'>Raised by the loss-prevention team (CCTV reviews, audits, hotline). Partial and sometimes wrong.</p>" + table(
        ["Flag", "Day", "Reported", "Store", "SKU", "Type", "Source", "Confirmed", "Loss"],
        ([r["flag_id"], service.day_str(r["day"]), service.day_str(r["reported_day"]), r["store_id"], link(f"/ledger?store={r['store_id']}&sku={r['sku_id']}", r["sku_id"]), r["flag_type"], r["source"], "yes" if r["confirmed"] else "no", f"£{r['loss_value_gbp']:.2f}"] for r in rows[:PAGE]),
        {8},
    ) + pager("/lp-flags", {}, p, len(rows) > PAGE) + "</div>"
    return render("Loss prevention", body, "/lp-flags")


@router.get("/tasks", response_class=HTMLResponse)
def tasks(status: str = "", page: int = 1) -> HTMLResponse:
    if (nr := _not_ready()) is not None:
        return nr
    p = max(1, page)
    sql, args = "SELECT * FROM tasks", []
    if status:
        sql += " WHERE status = ?"
        args.append(status)
    rows = db.conn().execute(sql + " ORDER BY created_at DESC, task_id DESC LIMIT ? OFFSET ?", [*args, PAGE + 1, (p - 1) * PAGE]).fetchall()
    tabs = " ".join(f'<a href="/tasks{"?status=" + s if s else ""}" class="chip">{e(s or "all")}</a>' for s in ["", *settings.TASK_STATUSES])
    body = f"<h1>Tasks from Sentinel</h1><div class='card'><p class='muted'>Raised by Inventory Sentinel after a person approved them. Work them here; Sentinel reads the outcome back.</p><p>{tabs}</p>" + table(
        ["Task", "Type", "Title", "Store", "SKU", "Priority", "Status", "Due", "Outcome", "Created"],
        ([link(f"/tasks/{r['task_id']}", r["task_id"]), r["type"], r["title"], r["store_id"], r["sku_id"] or "", chip(r["priority"], r["priority"]), chip(r["status"], r["status"]), r["due_by"] or "", r["outcome"] or "", r["created_at"]] for r in rows[:PAGE]),
    ) + pager("/tasks", {"status": status} if status else {}, p, len(rows) > PAGE) + "</div>"
    return render("Tasks", body, "/tasks")


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(task_id: str, error: str = "") -> HTMLResponse:
    if (nr := _not_ready()) is not None:
        return nr
    try:
        t = service.get_task(task_id)
    except service.VendorError as exc:
        raise HTTPException(404, exc.message) from exc
    opts = lambda values, cur: "".join(f'<option value="{e(v)}" {"selected" if v == cur else ""}>{e(v or "—")}</option>' for v in values)  # noqa: E731
    ev = t.get("evidence") or {}
    ev_html = "".join(f"<li><b>{e(str(k))}</b>: {e(str(v))}</li>" for k, v in ev.items()) if isinstance(ev, dict) else e(str(ev))
    ledger_link = f'<a href="/ledger?store={e(t["store_id"])}&sku={e(t["sku_id"] or "")}">Open the stock ledger</a>' if t["sku_id"] else ""
    body = f"""<h1>{e(t['task_id'])} · {e(t['title'])}</h1>
{f'<p class="bad">{e(error)}</p>' if error else ''}
<div class="card"><div class="row">{chip(t['type'])}{chip(t['priority'], t['priority'])}{chip(t['status'], t['status'])}<span class="muted">Store {e(t['store_id'])}{' · SKU ' + e(t['sku_id']) if t['sku_id'] else ''} · due {e(t['due_by'] or '—')}</span></div>
<p style="white-space:pre-wrap">{e(t['description'] or '')}</p>
<p class="muted">From Sentinel alert {e(t['source_alert_id'] or '—')} · SOP {e(t['sop_id'] or '—')} · ref {e(t['external_ref'] or '—')}</p>
{f'<ul>{ev_html}</ul>' if ev_html else ''}{ledger_link}</div>
<div class="card"><h2 style="margin-top:0">Update</h2>
<form method="post" action="/tasks/{e(t['task_id'])}" class="row" style="align-items:flex-end">
<label>Status<select name="status">{opts(settings.TASK_STATUSES, t['status'])}</select></label>
<label>Outcome<select name="outcome">{opts(['', *settings.TASK_OUTCOMES], t['outcome'] or '')}</select></label>
<label>Units found / corrected<input name="outcome_units" type="number" value="{'' if t['outcome_units'] is None else t['outcome_units']}"></label>
<label>Assignee<input name="assignee" value="{e(t['assignee'] or '')}"></label>
<label style="flex-basis:100%">Note<textarea name="note"></textarea></label>
<button>Save</button></form></div>
<div class="card"><h2 style="margin-top:0">History</h2>{table(["When", "Who", "What", "Note"], ([x['at'], x['actor'], x['event'], x['note'] or ''] for x in t['events']))}</div>"""
    return render(t["task_id"], body, "/tasks")


@router.post("/tasks/{task_id}")
def task_update(task_id: str, status: str = Form(""), outcome: str = Form(""), outcome_units: str = Form(""), assignee: str = Form(""), note: str = Form("")) -> RedirectResponse:
    try:
        units = int(outcome_units) if outcome_units.strip() else None
        service.update_task(task_id, status or None, outcome or None, units, note or None, assignee or None)
    except (service.VendorError, ValueError) as exc:
        msg = exc.message if isinstance(exc, service.VendorError) else "Units must be a whole number."
        return RedirectResponse(f"/tasks/{task_id}?{urlencode({'error': msg})}", status_code=303)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@router.get("/answer-key", response_class=HTMLResponse)
def answer_key_page(page: int = 1) -> HTMLResponse:
    if (nr := _not_ready()) is not None:
        return nr
    p = max(1, page)
    vis = service.visible_through()
    rows = db.conn().execute(
        "SELECT a.*, s.store_id, k.sku_id FROM answer_key a JOIN stores s USING(store_code) JOIN skus k USING(sku_code) WHERE day <= ? ORDER BY day DESC, store_code, sku_code LIMIT ? OFFSET ?",
        (vis, PAGE + 1, (p - 1) * PAGE),
    ).fetchall()
    body = "<h1>Demo answer key</h1><div class='card'><p class='muted'>Only a simulated vendor has this: the anomalies injected into the data, so presenters can check what Sentinel caught. Real systems never expose it.</p>" + table(
        ["Day", "Store", "SKU", "Injected anomaly", "Incident", "Units lost"],
        ([service.day_str(r["day"]), r["store_id"], link(f"/ledger?store={r['store_id']}&sku={r['sku_id']}", r["sku_id"]), r["truth_type"], r["truth_incident"], r["truth_loss_units"]] for r in rows[:PAGE]),
        {4, 5},
    ) + pager("/answer-key", {}, p, len(rows) > PAGE) + "</div>"
    return render("Demo answer key", body, "/answer-key")


@router.post("/admin/advance")
def advance(request: Request, days: int = Form(1)) -> RedirectResponse:
    service.advance(max(1, min(int(days), 60)))
    return RedirectResponse(request.headers.get("referer") or "/", status_code=303)


@router.post("/admin/reseed")
def reseed() -> RedirectResponse:
    seed.start_background(force=True)
    return RedirectResponse("/", status_code=303)
