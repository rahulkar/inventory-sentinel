---
id: data-feed-failure
title: Vendor data feed or scheduled run failure
version: "1.0"
summary: What to do when a sync or scheduled run fails, or the vendor's data stops moving forward, so no detection runs on fresh data.
applies_to: [feed_failure]
owner_role: Sentinel administrator
steps:
  - id: read-error
    text: "Open Schedules (or Data, Connectors) and read the failed run's error. The error kind tells you where to look: unreachable or timeout means network or vendor down; auth means the token; not_ready means the vendor is still loading; contract or no_data means the vendor changed or emptied its feed."
    role: Sentinel administrator
    due_hours: 4
    evidence: [Schedule run id and error text]
  - id: test-connection
    text: "Use Test connection on the connector. If it fails, check the URL and token, and whether the vendor's MCP endpoint is up. A vendor-side outage goes to the vendor's support desk with the time and error."
    role: Sentinel administrator
    due_hours: 8
  - id: stale-feed
    text: "If syncs succeed but warn that no new trading days arrived, the vendor's end-of-day close has not run. Ask the vendor's operations team to confirm the close. Do not retrain on a stale snapshot."
    role: Sentinel administrator
    due_hours: 24
  - id: rerun
    text: Once fixed, press Run now on the schedule. The next run collects any missed days automatically (each sync re-pulls recent days).
    role: Sentinel administrator
    due_hours: 24
  - id: tell-users
    text: If detection was missed for more than one business day, tell store and LP leads that alerts are delayed and when they will catch up.
    role: Sentinel administrator
    due_hours: 24
closure:
  - A successful sync and detection run after the fix.
  - The cause noted on the schedule run (or in the change log).
triage_mapping: {}
---

# Vendor data feed or scheduled run failure

Sentinel only sees what the vendor's system gives it. When the feed stops, alerts stop too, which is easy to mistake for
"no problems". Each failed run records an error kind:

| Error kind | Usual cause | First check |
|---|---|---|
| `unreachable`, `timeout` | Network, firewall, or the vendor endpoint down | Test connection; vendor status page |
| `auth` | Expired or wrong token | Update the connector's token |
| `not_ready` | Vendor still loading or closing the day | Wait and re-run |
| `contract`, `no_data` | Vendor changed fields or emptied the feed | Talk to the vendor; check capabilities |
| `model` | The chosen model no longer fits the data | Pick "retrain" or another model on the schedule |
| `internal` | A Sentinel bug or a full disk | Server log; free disk space |

A sync that succeeds with a warning ("no new trading days", "fewer rows than usual") is also a feed problem. Follow
the stale-feed step.
