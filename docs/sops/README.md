# Standard operating procedures (SOPs)

These files tell people what to do when Inventory Sentinel flags missing or unexplained inventory. The app reads them:

- the alert drill-down shows the SOP that matches the alert's likely type as a checklist, with the escalation level
  from the master SOP and "Raise vendor task" buttons for steps that have a task template;
- the assistant quotes them (`get_sop`, `find_sop`, and `search_docs`) and the MCP server serves them as `sentinel://sop/<id>`;
- scheduled runs use the step templates when they propose vendor tasks for new critical alerts.

Nothing in an SOP runs by itself. Every vendor task needs a person's approval.

## Files

| SOP | Covers |
|---|---|
| `missing-inventory-response.md` | Master procedure: triage, the escalation matrix, evidence, closure, feedback. Every other SOP builds on it. |
| `theft-external.md` | Losses consistent with shoplifting |
| `theft-internal.md` | Losses consistent with staff involvement (handled confidentially) |
| `scan-fraud.md` | Till patterns: voids, manual entries, overrides, refunds without stock |
| `counting-error.md` | A count that reverses the next day |
| `receiving-error.md` | Deliveries booked differently from what arrived |
| `data-entry-error.md` | Keying mistakes (x10 receipts, large adjustments) |
| `velocity-shift.md` | Sales stopping (possible phantom stock) or spiking |
| `unclear.md` | Anything the rules cannot type |
| `data-feed-failure.md` | Syncs or scheduled runs that fail, or a vendor feed that goes stale |
| `false-positive-handling.md` | Closing alerts that turn out to be nothing, so the model learns |

## Front matter

```yaml
---
id: counting-error                 # file-safe id, used in links and sentinel://sop/<id>
title: Counting error
version: "1.2"
summary: One line shown in lists.
applies_to: [counting_error]       # alert likely types this SOP handles
parent: missing-inventory-response # inherit escalation and closure from the master SOP
owner_role: Store manager
escalation:                        # master SOP only; the first matching rule wins
  - level: L3
    label: "L3: regional loss-prevention response"
    severities: [critical, high]   # empty = any severity
    min_value_gbp: 500
    response_hours: 4
    notify: [Regional LP manager]
steps:
  - id: recount
    text: Recount {sku_name} at {store_name} ...   # {placeholders} are filled from the alert
    role: Stock controller
    due_hours: 24
    evidence: [Recount sheet]
    vendor_task:                   # optional: offers a "Raise vendor task" button
      type: recount                # must be one of the vendor's task types
      priority: high               # optional; default follows severity
      title: "Recount {sku_name} at {store_name}"
      description: "..."           # optional; default describes the alert
closure: [What must be true to close]
triage_mapping:                    # how findings map onto the triage outcomes
  stock found: counting_error
---
```

Placeholders: `{store_id} {store_name} {region} {warehouse_team} {sku_id} {sku_name} {category} {start_date} {end_date}
{n_days} {units_at_risk} {value_at_risk_gbp} {likely_type} {likely_label} {severity} {p_true_pct} {reasons}`.

## Writing rules

- Describe patterns, never people. Write "consistent with internal loss", never "staff theft by X". An alert is a
  reason to look, not evidence of wrongdoing.
- Keep the first step cheap (recount, check paperwork) before anything intrusive (CCTV, interviews).
- Every SOP ends by recording the outcome in Sentinel's triage. That feedback trains the re-ranker.
- Change `version` whenever the steps change. Teams quote it in their notes.
