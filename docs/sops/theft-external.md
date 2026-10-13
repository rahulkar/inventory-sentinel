---
id: theft-external
title: Loss consistent with external theft (shoplifting)
version: "1.0"
summary: Stock disappears over several days with no matching sale, return, transfer or adjustment, usually on high-risk lines.
applies_to: [theft_external]
parent: missing-inventory-response
owner_role: Store manager
steps:
  - id: recount
    text: "Recount {sku_name} at {store_name} (floor, stockroom, fitting rooms, returns cage). Note any empty packaging or removed security tags."
    role: Stock controller
    due_hours: 24
    evidence: [Recount sheet, Photos of empty packaging or tags found]
    vendor_task:
      type: recount
      title: "Recount {sku_name} at {store_name} (possible external loss)"
      description: "About {units_at_risk} units (£{value_at_risk_gbp}) of {sku_name} ({sku_id}) unaccounted for between {start_date} and {end_date}. Count all locations and note empty packaging or removed tags."
  - id: cctv
    text: "If the recount confirms the loss and the level is L2 or above, an LP investigator reviews CCTV for the sales floor around {sku_name}'s fixture on {start_date} to {end_date}. Record time references only."
    role: Loss-prevention investigator
    due_hours: 48
    evidence: [CCTV time references, Investigator notes]
    vendor_task:
      type: cctv_review
      priority: high
      title: "CCTV review: {sku_name} fixture at {store_name}, {start_date} to {end_date}"
  - id: protect
    text: "Reduce exposure while you investigate: move {sku_name} closer to the till or a staffed area, check tagging, and brief the floor team on customer service (greeting, fitting-room counts). Do not brief on suspects."
    role: Store manager
    due_hours: 72
    evidence: [Merchandising change noted]
  - id: record
    text: Record the outcome in Sentinel. If the loss is confirmed, it is confirmed theft. If the stock turned up, it is a counting error.
    role: Store manager
    due_hours: 72
closure:
  - Loss confirmed or disproved by the recount.
  - Any CCTV review referenced on the task, with no footage attached.
  - Protective measures recorded where the loss was confirmed.
triage_mapping:
  loss confirmed: confirmed_theft
  stock found: counting_error
  nothing missing: false_alarm
---

# Loss consistent with external theft

**Pattern Sentinel saw:** expected stock is higher than counted stock for several days in a row. No sale, return,
transfer or adjustment explains it, often on high-theft-risk or untagged lines. Till signals are normal, so this is
not scan fraud.

**Typical explanations:** shoplifting, items hidden or misplaced on the floor, a missed transfer.

Always recount first. Only an L2+ investigator decides on a CCTV review, and nobody is approached on the strength of
the alert. If the store has repeated external-loss alerts on the same category, raise a `process_review` vendor task
for merchandising and security tagging.
