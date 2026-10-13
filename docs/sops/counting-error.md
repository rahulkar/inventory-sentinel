---
id: counting-error
title: Counting error
version: "1.0"
summary: A one-day dip in the count that reverses the next day. Usually a miscount or stock in an unexpected place.
applies_to: [counting_error]
parent: missing-inventory-response
owner_role: Store stock controller
steps:
  - id: check-reversal
    text: "Open the drill-down: if the count on the day after {end_date} came back to normal, the stock was never lost. Note where it was found if anyone knows."
    role: Stock controller
    due_hours: 24
    evidence: [Drill-down screenshot or ledger extract]
  - id: recount
    text: If the dip did not reverse, recount {sku_name} at {store_name} in every location.
    role: Stock controller
    due_hours: 24
    evidence: [Recount sheet]
    vendor_task:
      type: recount
      priority: normal
      title: "Recount {sku_name} at {store_name} (possible miscount)"
      description: "The count of {sku_name} ({sku_id}) dropped by about {units_at_risk} units around {start_date} and may have reversed. Recount all locations and record where the stock was."
  - id: fix-cause
    text: "If miscounts repeat on this SKU or area, fix the cause: shelf-edge labels, a second location not on the count list, or RFID read gaps. Raise a process review if needed."
    role: Store manager
    due_hours: 168
  - id: record
    text: Record the outcome in Sentinel as a counting error (or as a false alarm if nothing was wrong).
    role: Stock controller
    due_hours: 72
closure:
  - The count is confirmed correct, or corrected with evidence.
  - Any repeated cause has an owner.
triage_mapping:
  miscount confirmed: counting_error
  nothing wrong: false_alarm
---

# Counting error

**Pattern Sentinel saw:** the evening count dropped for one day and then came back. Book and physical stock agree
again afterwards.

**Typical explanations:** stock in a second location missed by the counter, RFID read gaps, items in fitting rooms
at count time.

This is the cheapest alert to close. Most of the time the drill-down already shows the reversal. Do not post a stock
adjustment for a dip that reversed by itself.
