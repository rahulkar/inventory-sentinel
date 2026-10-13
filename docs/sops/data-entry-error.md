---
id: data-entry-error
title: Data-entry error
version: "1.0"
summary: A one-off keying mistake, such as receipts booked x10 or a large manual adjustment, that throws the book stock out.
applies_to: [data_entry_error]
parent: missing-inventory-response
owner_role: Inventory control (head office)
steps:
  - id: find-entry
    text: "Find the transaction for {sku_name} at {store_name} on {start_date}: a receipt or adjustment far larger than usual. Note who keyed it and the reason code (for the correction record, not for blame)."
    role: Inventory control
    due_hours: 24
    evidence: [Transaction reference]
  - id: correct
    text: Correct the entry in the vendor system with a reversing transaction and a reason. The person who made the original entry does not post the fix.
    role: Inventory control
    due_hours: 48
    evidence: [Correction reference]
    vendor_task:
      type: data_correction
      priority: normal
      title: "Correct stock entry: {sku_name} at {store_name}, {start_date}"
      description: "A receipt or adjustment for {sku_name} ({sku_id}) on {start_date} looks mis-keyed (book stock out by about {units_at_risk} units). Check the transaction and post a reversing correction with a reason."
  - id: prevent
    text: If the same kind of mistake repeats, add a sense-check (quantity limit or confirmation prompt) or retrain on pack sizes.
    role: Inventory control
    due_hours: 168
  - id: record
    text: Record the outcome in Sentinel as a process issue.
    role: Inventory control
    due_hours: 72
closure:
  - Correction posted and referenced on the task.
triage_mapping:
  mis-key confirmed: process_issue
  nothing wrong: false_alarm
---

# Data-entry error

**Pattern Sentinel saw:** one day with a receipt or adjustment many times the SKU's normal size. Book and counted stock
split apart from that day on.

**Typical explanations:** an extra zero, the wrong SKU or store selected, pack quantity typed as units.

No physical loss is involved, so do not escalate to loss prevention. Correct the book, then find out why the system
allowed it.
