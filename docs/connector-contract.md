# Sentinel Inventory Connector contract (v1)

Inventory Sentinel reads a retailer's stock data, and sends approved tasks back, through an **MCP server** that the
vendor (or an integrator) runs in front of their inventory system. Any system can be connected by writing a small MCP
adapter that implements the tools below over streamable HTTP. The bundled demo back-office (`vendor_mock/`) is a
complete reference implementation.

- **Transport:** MCP streamable HTTP, e.g. `https://vendor.example.com/mcp/`.
- **Authentication:** an optional bearer token. The header name and scheme are configurable per connector, and Sentinel
  sends `Authorization: Bearer <token>` by default.
- **Results:** every tool returns one JSON object. On failure it returns `{"error": {"code": "...", "message": "..."}}`.
  Codes: `not_ready`, `bad_request`, `bad_cursor`, `not_found`, `unauthorized`.
- **Dates:** ISO `YYYY-MM-DD` in the vendor's business time zone. A day appears only once it has closed (end-of-day
  stock count done).
- **Ids:** `store_id` and `sku_id` are the vendor's own stable string ids.

## Why a contract, and what Sentinel does with it

Sentinel's detectors are unsupervised: they learn what "normal" looks like from **each vendor's own history** and flag
what deviates from it. On every sync Sentinel:

1. pulls only new days, plus a few recent days to pick up late corrections, into a local copy;
2. builds a snapshot of the last *N* days (120 by default) and trains or scores on it;
3. reads back the outcomes of tasks it raised and turns them into team feedback.

Bulk data never goes through the language model; the assistant only sees summaries.

## Tools

### `get_capabilities()`

What the vendor supports. Sentinel calls it on "Test connection" and at the start of every sync.

```json
{
  "contract": "sentinel-inventory-connector", "version": "1.0",
  "vendor": {"name": "Demo Retail Co.", "system": "..."}, "status": "ready",
  "timezone": "Europe/London", "currency": "GBP",
  "data_range": {"first_date": "2026-05-16", "last_date": "2026-10-12"}, "business_date": "2026-10-13",
  "counts": {"stores": 40, "skus": 250},
  "paging": {"default_page_size": 50000, "max_page_size": 100000}, "encodings": ["columnar-json"],
  "fields": {"daily": ["opening_stock", "received_units", "sold_units", "...", "counted_closing", "on_promo"]},
  "features": {"lp_flags": true, "tasks": true, "live_lookup": true, "answer_key": false},
  "task_types": ["recount", "investigate", "cctv_review", "receiving_check", "till_audit", "data_correction", "process_review"],
  "backoffice_url": "https://vendor.example.com/"
}
```

- `status` is `ready`, or `seeding` / `loading` while the vendor prepares its data. Sentinel only syncs when it is `ready`.
- `fields.daily` lists the measures this vendor can supply. **Required:** `counted_closing`, plus either
  `expected_closing` or both `opening_stock` and `sold_units`. All other measures are optional and sharpen detection:
  `received_units`, `returned_units`, `transfer_in_units`, `transfer_out_units`, `adjustment_units`, `pos_scans`,
  `manual_entry_scans`, `void_count`, `override_count`, `after_hours_scans`, `receiving_scans`, `on_promo`.
- `features.answer_key` is **demo only**. A simulated vendor may expose the anomalies it injected so that Sentinel can
  score itself. Real systems set it to `false`.

### `list_stores(cursor?, page_size?)` and `list_skus(cursor?, page_size?)`

Both return `{"items": [...], "next_cursor": "..." | null}`.

- **Store fields** Sentinel uses: `store_id`, `store_name`, `region`, `format`, `warehouse_team`.
- **SKU fields:** `sku_id`, `sku_name`, `category`, `unit_cost` (needed to value losses), and optionally `unit_price`
  and `high_theft_risk`.

### `get_daily_movements(since, until?, fields?, cursor?, page_size?)`

One row per store, SKU and closed day, for days in `[since, until]`. `until` defaults to the last closed day. Results
are **columnar** and **dictionary-encoded**, so a 50,000-row page is a few MB:

```json
{
  "since": "2026-10-09", "until": "2026-10-12", "as_of": "2026-10-13",
  "columns": ["date", "store_id", "sku_id", "opening_stock", "..."],
  "row_count": 50000, "next_cursor": "eyJzIjo...", "encoding": "columnar-json",
  "data": {
    "date": {"dict": ["2026-10-09", "2026-10-10"], "idx": [0, 0, 0, 1, ...]},
    "store_id": {"dict": ["S001", "S002"], "idx": [0, 0, 1, ...]},
    "sku_id": {"dict": ["K00001", "K00002"], "idx": [0, 1, 0, ...]},
    "opening_stock": [12, 40, 7, ...]
  }
}
```

Rows are ordered by `(date, store_id, sku_id)`. The cursor is opaque. It must freeze `until`, so that paging stays
consistent while the vendor closes another day. Pass `next_cursor` back with the same arguments until it is `null`.

### `get_lp_flags(since?, until?, cursor?, page_size?)`

Loss-prevention flags reported so far for days in the range: `{"items": [{flag_id, date, store_id, sku_id, flag_type,
source, confirmed, loss_value_gbp, reported_on}], "next_cursor"}`. Flags are partial, noisy labels. Sentinel uses them
to judge models when no better labels exist, and leaves flagged days out of training.

### `get_stock_position(store_id, sku_id, days=7)`

A **live** lookup used by the assistant and the alert drill-down. It returns the on-hand count and up to 14 days of
movements, with an `as_of` date.

### `create_task(type, store_id, title, description?, priority?, idempotency_key?, sku_id?, external_ref?, source_alert_id?, sop_id?, evidence?, due_by?)`

Raises a task for store staff in the vendor's own workflow tool. It returns `{"task_id", "status", "created",
"created_at"}`. **A repeat call with the same `idempotency_key` must return the existing task** (`"created": false`).
Sentinel uses `<alert_key>:<type>` as the key, so retries never duplicate work. Sentinel only calls this after a person
has approved the task in the app.

- **Types** (as advertised in `task_types`): `recount`, `investigate`, `cctv_review`, `receiving_check`, `till_audit`,
  `data_correction`, `process_review`.
- **Priorities:** `low`, `normal`, `high`, `urgent`.

### `list_tasks(status?, store_id?, external_ref?, updated_since?, cursor?, page_size?)` and `get_task(task_id)`

Task status and outcome, read back on every sync:

- **Statuses:** `open`, `acknowledged`, `in_progress`, `done`, `rejected`.
- **Outcomes:** `confirmed_loss`, `count_corrected`, `process_fixed`, `no_issue`, plus `outcome_units` and `outcome_note`.

Sentinel maps a closed task's outcome to a team decision (triage) for its alert:

| Task outcome | Triage decision |
|---|---|
| `confirmed_loss` | confirmed theft (theft-type alerts), otherwise process issue |
| `count_corrected` | counting error |
| `process_fixed` | process issue |
| `no_issue` | false alarm |

### `get_answer_key(since?, until?, cursor?, page_size?)` (demo vendors only)

Same columnar shape as `get_daily_movements`, with `truth_type`, `truth_incident` and `truth_loss_units`. Never a
model input.

## Writing an adapter for a real system

1. Map the system's stock ledger to the daily measures: expected (book) and counted closing stock are the minimum.
   Deliveries, sales, returns, transfers, adjustments and till exceptions add signal.
2. Serve closed days only. Use the business date, not the wall clock.
3. Implement keyset paging on `(date, store_id, sku_id)` with a frozen `until`.
4. Map `create_task` onto the system's task or work-order API, and honour `idempotency_key`.
5. Test it against the contract checks in `vendor_mock/tests/smoke.py`, by pointing that script's MCP calls at your URL.
