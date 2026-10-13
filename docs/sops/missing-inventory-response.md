---
id: missing-inventory-response
title: Missing inventory response (master procedure)
version: "1.0"
summary: What to do whenever Sentinel flags unexplained stock loss. Covers triage, escalation, evidence, closure and feedback.
applies_to: []
owner_role: Head of loss prevention
escalation:
  - level: L3
    label: "L3: regional loss-prevention response"
    severities: [critical, high]
    min_value_gbp: 500
    response_hours: 4
    notify: [Regional loss-prevention manager, Store manager, Area manager]
  - level: L3
    label: "L3: regional loss-prevention response"
    severities: [critical]
    min_value_gbp: 100
    response_hours: 4
    notify: [Regional loss-prevention manager, Store manager]
  - level: L2
    label: "L2: store manager and loss prevention"
    severities: [critical]
    min_value_gbp: 0
    response_hours: 24
    notify: [Store manager, Loss-prevention investigator]
  - level: L2
    label: "L2: store manager and loss prevention"
    severities: [high]
    min_value_gbp: 100
    response_hours: 24
    notify: [Store manager, Loss-prevention investigator]
  - level: L2
    label: "L2: store manager and loss prevention"
    severities: [medium]
    min_value_gbp: 500
    response_hours: 24
    notify: [Store manager, Loss-prevention investigator]
  - level: L1
    label: "L1: store team check"
    severities: []
    min_value_gbp: 0
    response_hours: 72
    notify: [Store stock controller]
steps:
  - id: acknowledge
    text: Acknowledge the alert in Sentinel and note who owns it. Check the drill-down for the dates, units and reasons, and whether a vendor task is already open for it.
    role: Alert owner
    due_hours: 4
    evidence: [Owner named on the alert]
  - id: verify-stock
    text: "Physically verify {sku_name} ({sku_id}) at {store_name}: shop floor, stockroom, returns cage and transfers in transit. Most flags are settled here."
    role: Stock controller
    due_hours: 24
    evidence: [Recount sheet with counter name and time]
    vendor_task:
      type: recount
      title: "Recount {sku_name} at {store_name}"
      description: "Sentinel flagged about {units_at_risk} units (£{value_at_risk_gbp}) of {sku_name} ({sku_id}) unexplained between {start_date} and {end_date}. Count shop floor, stockroom, returns and in-transit stock and record the result."
  - id: follow-type-sop
    text: If stock is still missing after the recount, follow the SOP for the likely type ({likely_label}) and escalate to the level shown.
    role: Alert owner
    due_hours: 24
  - id: record-outcome
    text: Record the outcome in Sentinel (Act, Triage) or close the vendor task with an outcome. Sentinel reads closed tasks back as team feedback.
    role: Alert owner
    due_hours: 72
    evidence: [Outcome recorded in Sentinel or on the vendor task]
closure:
  - The stock was found (record the outcome as a counting error), explained (process issue) or confirmed lost.
  - Any stock correction was posted in the vendor system by someone other than the person who counted.
  - The outcome is recorded in Sentinel's triage or on the closed vendor task.
triage_mapping:
  stock found or count corrected: counting_error
  booking, receiving or process fault: process_issue
  loss confirmed (theft or fraud): confirmed_theft
  nothing wrong: false_alarm
---

# Missing inventory response (master procedure)

## Purpose

Sentinel ranks store-SKU-days whose stock movements look unusual and groups them into alerts. **An alert is a reason to
look, not evidence of wrongdoing.** Most alerts are explained by a miscount, a booking error or a delivery problem.
This procedure makes sure every alert gets a proportionate, consistent and documented response, and that the result
flows back into Sentinel so it ranks better next time.

## When it applies

To every alert from a detection run, whether a person or a scheduled run started it. The type SOP for the alert's
likely type adds the specific checks. If the type is "unclear", use the *unclear* SOP.

## Escalation matrix

Severity comes from Sentinel's alert. Value at risk is the alert's estimated unexplained units × unit cost.

| Severity \ value at risk | under £100 | £100 to £500 | over £500 |
|---|---|---|---|
| **Critical** | L2 (24 h) | L3 (4 h) | L3 (4 h) |
| **High** | L1 (72 h) | L2 (24 h) | L3 (4 h) |
| **Medium** | L1 (72 h) | L1 (72 h) | L2 (24 h) |

- **L1: store team check.** The stock controller recounts and records the result. No one else is involved unless the
  recount confirms a loss.
- **L2: store manager and loss prevention.** The store manager owns the alert, and a loss-prevention investigator
  reviews the evidence before anything intrusive (CCTV, interviews) happens.
- **L3: regional loss-prevention response.** The regional loss-prevention manager is told within the response time
  and decides whether to secure evidence, involve HR, or (rarely) the police.

Repeat alerts on the same store and SKU within 28 days go up one level.

## Evidence

Keep evidence with the vendor task or the case file, not in chat:

- recount sheets (who counted, when, and where they looked);
- delivery notes, goods-in scans and transfer paperwork;
- till reports (voids, manual entries, overrides, refunds) for the alert dates;
- CCTV references, never the footage itself, only when the type SOP calls for it and L2 or above approves.

## Do not

- Do not confront or name any individual on the strength of an alert.
- Do not post stock corrections before the recount evidence is filed.
- Do not close an alert without an outcome. "No time to check" is not a closure; reassign it.

## Feedback

When you record outcomes, Sentinel's feedback re-ranker learns which kinds of alerts are real in your stores. Closed
vendor tasks count: each sync reads their outcomes back (confirmed loss, count corrected, process fixed, no issue)
and turns them into triage decisions.
