---
id: theft-internal
title: Loss consistent with internal involvement (confidential)
version: "1.0"
summary: Several valuable lines lose stock on the same nights, together with after-hours scanning. Handle confidentially through loss prevention.
applies_to: [theft_internal]
parent: missing-inventory-response
owner_role: Regional loss-prevention manager
steps:
  - id: restrict
    text: "Treat this alert as confidential. Only the store manager and loss prevention see it. Do not discuss it with the wider store team, and do not raise a store-visible recount that names the dates."
    role: Store manager
    due_hours: 4
    evidence: [Access limited to named people]
  - id: lp-review
    text: "A loss-prevention investigator reviews after-hours access logs, alarm set/unset times and the after-hours scans for {store_name} on {start_date} to {end_date}, alongside the other SKUs that lost stock on the same nights."
    role: Loss-prevention investigator
    due_hours: 24
    evidence: [Access and alarm logs, List of SKUs affected on the same nights]
    vendor_task:
      type: investigate
      priority: urgent
      title: "Confidential LP review: {store_name}, {start_date} to {end_date}"
      description: "Sentinel saw losses on several valuable lines on the same nights together with after-hours scanning, a pattern consistent with internal loss. For loss prevention only: review access, alarm and scan logs. Do not share with the store team."
  - id: discreet-count
    text: Arrange a discreet count of the affected lines by someone from outside the store (area stock team or LP), not the usual counter.
    role: Loss-prevention investigator
    due_hours: 48
    evidence: [Independent count sheet]
  - id: hr
    text: Only if the evidence supports it, the regional LP manager involves HR under the company's investigation policy. Sentinel's alert alone is never grounds for action against a person.
    role: Regional loss-prevention manager
    due_hours: 120
  - id: record
    text: Record the outcome in Sentinel without personal details (confirmed theft, process issue or false alarm).
    role: Regional loss-prevention manager
    due_hours: 168
closure:
  - Investigation closed by the regional LP manager, with case notes held in the LP system, not Sentinel.
  - Outcome recorded in Sentinel without names.
triage_mapping:
  internal loss confirmed: confirmed_theft
  explained by process (late delivery, cleaning, stock moves): process_issue
  nothing found: false_alarm
---

# Loss consistent with internal involvement

**Pattern Sentinel saw:** on one or a few nights, several valuable SKUs in one store lost stock together, along with
scanning or system activity after closing time.

**Typical explanations:** genuine internal loss, but also late deliveries processed after hours, stock moves between
stores or areas, or a cleaning or contractor visit. Rule those out before assuming loss.

This is the most sensitive SOP:

- **Confidential from the start.** Raise only the `investigate` task, which goes to loss prevention. Do not raise a
  store-visible recount task that reveals the dates.
- **Independent counting.** Someone from outside the store does the count.
- **No action against people on an alert.** HR is involved only on evidence gathered under company policy.
- **No names in Sentinel.** Keep case notes in the LP case system.
