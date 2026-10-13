---
id: false-positive-handling
title: Closing false alarms so the model learns
version: "1.0"
summary: How to close alerts that turn out to be nothing, and how those closures improve the ranking.
applies_to: [false_alarm]
owner_role: Store manager
steps:
  - id: confirm
    text: Confirm there is nothing wrong. The recount matches the book (or the dip reversed), and the movement has a normal explanation (promotion, delivery timing, a known event).
    role: Stock controller
    due_hours: 24
    evidence: [Recount or ledger extract]
  - id: record
    text: "Record it in Sentinel as false alarm, with a short reason in the note (e.g. 'promo started early', 'delivery booked next day'). On a vendor task, close it with outcome no_issue."
    role: Store manager
    due_hours: 24
  - id: patterns
    text: "If the same false alarm keeps coming back (same store, SKU or reason), tell the Sentinel administrator. Once there are at least 30 reviewed alerts, retraining with team feedback lowers this kind of alert."
    role: Store manager
    due_hours: 168
closure:
  - Outcome recorded as false alarm with a reason.
triage_mapping:
  nothing wrong: false_alarm
---

# Closing false alarms

False alarms are useful. Each one recorded tells Sentinel's feedback re-ranker what "normal but unusual" looks like
in your stores. Close them honestly and quickly. An alert left open helps nobody, and one closed as "confirmed" to
make it go away teaches the model the wrong thing.
