---
id: receiving-error
title: Receiving error (delivery booked differently from what arrived)
version: "1.0"
summary: A delivery day where booked receipts and goods-in scans disagree, or stock goes missing straight after a delivery.
applies_to: [receiving_error]
parent: missing-inventory-response
owner_role: Receiving supervisor
steps:
  - id: paperwork
    text: "Find the delivery for {sku_name} at {store_name} on or just before {start_date}: delivery note, advance shipping notice, goods-in scans and any signed discrepancy note."
    role: Receiving supervisor
    due_hours: 24
    evidence: [Delivery note, Goods-in scan log]
    vendor_task:
      type: receiving_check
      priority: high
      title: "Receiving check: {sku_name} delivery to {store_name} around {start_date}"
      description: "Booked receipts and goods-in scans for {sku_name} ({sku_id}) disagree by about {units_at_risk} units around {start_date}. Check the delivery note, ASN and scans, and whether a short or over delivery was signed for."
  - id: recount
    text: Recount the SKU to confirm what physically arrived.
    role: Stock controller
    due_hours: 24
    vendor_task:
      type: recount
      title: "Recount {sku_name} at {store_name} after delivery"
  - id: claim
    text: "If the delivery was short, raise a claim with the distribution centre or supplier within their claim window, and correct the receipt in the vendor system (someone other than the receiver does this)."
    role: Store manager
    due_hours: 72
    evidence: [Claim reference]
  - id: record
    text: Record the outcome in Sentinel as a process issue (receiving), or a counting error if the stock was there all along.
    role: Receiving supervisor
    due_hours: 72
closure:
  - Receipt corrected or confirmed.
  - Supplier or DC claim raised where the delivery was short.
triage_mapping:
  short or over delivery confirmed: process_issue
  stock found: counting_error
  nothing wrong: false_alarm
---

# Receiving error

**Pattern Sentinel saw:** on a delivery day the booked receipts don't match the goods-in scans, or stock that was booked in
is missing at the next count.

**Typical explanations:** short delivery signed as complete, cartons booked to the wrong SKU or store, a pack-size
mix-up (a pack of 6 booked as 1).

Act fast. Supplier and DC claim windows are short.
