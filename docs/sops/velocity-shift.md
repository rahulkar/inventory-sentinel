---
id: velocity-shift
title: Sales stopped or spiked (possible phantom stock)
version: "1.0"
summary: An item that normally sells every day suddenly stops (stock on the books but not on the shelf) or jumps far above normal.
applies_to: [velocity_shift]
parent: missing-inventory-response
owner_role: Store manager
steps:
  - id: shelf-check
    text: "Check whether {sku_name} is actually on the shelf at {store_name}: is it out of stock on the floor while the system shows stock (phantom stock), or in the wrong place?"
    role: Store team
    due_hours: 24
    evidence: [Shelf check note or photo]
    vendor_task:
      type: recount
      priority: high
      title: "Shelf check and recount: {sku_name} at {store_name} (sales stopped)"
      description: "{sku_name} ({sku_id}) normally sells daily but sales stopped or spiked from {start_date}. Check the shelf, the stockroom and price labels, then recount and correct the book stock if it is phantom."
  - id: correct-book
    text: If the shelf is empty and the count confirms it, correct the book stock so replenishment can order again (record the units written off).
    role: Stock controller
    due_hours: 48
  - id: spike
    text: If sales spiked instead, check for a mispriced promotion, a local event, or bulk buying, and tell the buying team if it will continue.
    role: Store manager
    due_hours: 72
  - id: record
    text: "Record the outcome in Sentinel: process issue for phantom stock or pricing, false alarm for genuine demand."
    role: Store manager
    due_hours: 72
closure:
  - Book stock matches the shelf.
  - Replenishment is unblocked.
triage_mapping:
  phantom stock or mispricing: process_issue
  stock missing (loss): confirmed_theft
  genuine demand change: false_alarm
---

# Sales stopped or spiked

**Pattern Sentinel saw:** a fast-selling item suddenly stopped selling while the books still show stock, or its sales
jumped well beyond normal promotions.

**Typical explanations:** phantom stock (the system thinks it's there, so nothing is reordered), stock stuck in the
stockroom or wrongly located, a wrong price, a genuine demand change.

Phantom stock costs sales every day it lasts, so treat the shelf check as urgent even when the value at risk looks small.
