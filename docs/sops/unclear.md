---
id: unclear
title: Unexplained stock movement (type unclear)
version: "1.0"
summary: Sentinel flags the movement as unusual but its rules cannot say what kind of problem it is. Start with a recount and the paperwork.
applies_to: [unclear]
parent: missing-inventory-response
owner_role: Store manager
steps:
  - id: recount
    text: Recount {sku_name} at {store_name} in every location.
    role: Stock controller
    due_hours: 24
    evidence: [Recount sheet]
    vendor_task:
      type: recount
      title: "Recount {sku_name} at {store_name}"
  - id: paperwork
    text: "Check deliveries, transfers, adjustments and till exceptions for {start_date} to {end_date} in the stock ledger. Whichever looks wrong points to the type SOP to follow next."
    role: Store manager
    due_hours: 48
    evidence: [Ledger extract with notes]
  - id: escalate
    text: If the loss is confirmed and nothing explains it, an LP investigator reviews it at the escalation level shown.
    role: Loss-prevention investigator
    due_hours: 72
    vendor_task:
      type: investigate
      priority: normal
      title: "Investigate unexplained loss: {sku_name} at {store_name}"
  - id: record
    text: Record what you found in Sentinel. The outcome teaches the re-ranker what this kind of alert usually is.
    role: Store manager
    due_hours: 72
closure:
  - Outcome recorded, with the type it turned out to be in the note.
triage_mapping:
  loss confirmed: confirmed_theft
  stock found: counting_error
  booking or process fault: process_issue
  nothing wrong: false_alarm
---

# Unexplained stock movement

Sentinel's anomaly score is high, but the pattern does not match one of its typed rules. Treat it like any other alert:
recount first, then read the ledger. If you find the cause, say so in the outcome note, because that is how unclear
alerts become typed ones over time.
