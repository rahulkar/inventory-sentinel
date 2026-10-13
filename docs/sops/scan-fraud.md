---
id: scan-fraud
title: Till pattern consistent with scan or refund fraud
version: "1.0"
summary: Stock loss together with unusual voids, manual entries, price overrides or refunds with no stock returned.
applies_to: [scan_fraud]
parent: missing-inventory-response
owner_role: Loss-prevention investigator
steps:
  - id: till-audit
    text: "Pull the till reports for {sku_name} at {store_name} on {start_date} to {end_date}: voids, manual (keyed) entries, price overrides and refunds, by till and by time. Compare with the same weekdays in previous weeks."
    role: Loss-prevention investigator
    due_hours: 24
    evidence: [Till exception report, Comparison with previous weeks]
    vendor_task:
      type: till_audit
      priority: high
      title: "Till audit: {sku_name} at {store_name}, {start_date} to {end_date}"
      description: "Sentinel saw stock loss on {sku_name} ({sku_id}) together with unusual voids, keyed entries, overrides or refunds without returned stock. Pull the exception report by till and time for these dates."
  - id: refund-check
    text: "For refunds in the period, check that the refunded stock was physically returned (the returns cage and returns log) and that receipts match."
    role: Store manager
    due_hours: 48
    evidence: [Returns log extract]
  - id: recount
    text: Recount {sku_name} so the loss is quantified before any conclusion.
    role: Stock controller
    due_hours: 24
    vendor_task:
      type: recount
      title: "Recount {sku_name} at {store_name}"
  - id: controls
    text: "If the pattern is confirmed, apply till controls with the area manager: supervisor sign-off on voids and refunds above a threshold, and keyed-entry limits on this SKU. Raise a process review if the cause is training."
    role: Store manager
    due_hours: 120
    vendor_task:
      type: process_review
      priority: normal
      title: "Till controls review at {store_name}"
  - id: record
    text: Record the outcome in Sentinel. A confirmed fraud is confirmed theft. A training or process gap is a process issue.
    role: Loss-prevention investigator
    due_hours: 120
closure:
  - Till audit filed with the task.
  - Refunds reconciled against returned stock.
  - Controls or training actions recorded.
triage_mapping:
  fraud confirmed: confirmed_theft
  training or process gap: process_issue
  normal activity (e.g. promotion pricing): false_alarm
---

# Till pattern consistent with scan or refund fraud

**Pattern Sentinel saw:** stock loss on a SKU at the same time as till exceptions: voids, keyed entries, price
overrides, or refunds where no stock came back.

**Typical explanations:** sweethearting (items passed without scanning), refund fraud, but also scanner faults (lots of
keyed entries), promotion price set-up errors (overrides) and new staff still learning.

Start with the till report, not CCTV. Compare like-for-like weekdays. A broken scanner or a mispriced promotion shows
up across every till, while fraud usually concentrates on certain tills or times.
