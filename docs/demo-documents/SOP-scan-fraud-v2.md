---
id: scan-fraud
title: Till pattern consistent with scan or refund fraud
version: "2.0"
summary: Stock loss together with unusual voids, keyed entries, price overrides or refunds with no stock returned. Version 2.0 adds the exception-report review and the GBP 20 void control from the Till Controls policy (RET-POL-007).
applies_to: [scan_fraud]
parent: missing-inventory-response
owner_role: Loss-prevention investigator
steps:
  - id: exception-report
    text: "Store manager reviews the daily till exception report for {store_name} on {start_date} to {end_date}: voids above GBP 20, keyed entries, price overrides, refunds without receipt and no-sale openings, by till and time (Till Controls policy RET-POL-007)."
    role: Store manager
    due_hours: 4
    evidence: [Till exception report]
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
    text: "For refunds in the period, check that the refunded stock was physically returned (the returns cage and returns log) and that receipts match. Refunds without receipt above GBP 250 need the store manager's approval on file."
    role: Store manager
    due_hours: 48
    evidence: [Returns log extract, Refund approvals]
  - id: recount
    text: Recount {sku_name} so the loss is quantified before any conclusion.
    role: Stock controller
    due_hours: 24
    vendor_task:
      type: recount
      title: "Recount {sku_name} at {store_name}"
  - id: cctv
    text: "Only if the till audit shows a concentration on certain tills or times, a loss-prevention investigator reviews the till cameras for those transactions, following the CCTV and Evidence Handling Guideline (LP-GDL-003)."
    role: Loss-prevention investigator
    due_hours: 72
    evidence: [Evidence log entry]
  - id: controls
    text: "If the pattern is confirmed, apply till controls with the area manager: supervisor key on voids above GBP 20 and on refunds, keyed-entry limits on this SKU, and a refresher for the team if the cause is training."
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
  - Exception report and till audit filed with the task.
  - Refunds reconciled against returned stock.
  - Controls or training actions recorded.
triage_mapping:
  fraud confirmed: confirmed_theft
  training or process gap: process_issue
  normal activity (e.g. promotion pricing or a scanner fault): false_alarm
---

# Till pattern consistent with scan or refund fraud (version 2.0)

**What changed in 2.0:** a same-day review of the till exception report by the store manager, the GBP 20 void control
and the GBP 250 no-receipt refund limit from the Till Controls, Voids and Refunds Policy (RET-POL-007), and a CCTV step
that only follows a till audit showing a concentration on certain tills or times.

**Pattern Sentinel saw:** stock loss on a SKU at the same time as till exceptions: voids, keyed entries, price
overrides, or refunds where no stock came back.

**Typical explanations:** sweethearting (items passed without scanning), refund fraud, but also scanner faults (lots of
keyed entries), promotion price set-up errors (overrides) and new staff still learning.

Start with the exception report and the till audit, not CCTV. Compare like-for-like weekdays. A broken scanner or a
mispriced promotion shows up across every till, while fraud usually concentrates on certain tills or times.
