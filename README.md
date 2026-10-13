# Inventory Sentinel: inventory anomaly detection

Inventory Sentinel finds unusual stock movements in a retailer's daily **store x SKU** records, read straight from
their inventory system over **MCP**. It catches stock that goes missing, till behaviour that does not add up,
miscounts, deliveries booked in wrong, typing mistakes and items that stop selling while the system says they are in
stock. It turns them into alerts with plain reasons, shows trends by store and category, and plans investigator time
with an expected return. It tells teams what to do next from **standard operating procedures**, raises approved
recounts and investigations back in the vendor's own system, runs all of this on a **schedule**, and learns from what
warehouse teams find.

It runs locally as one web app: a FastAPI + numpy / scikit-learn / LightGBM backend, a React + TypeScript UI, and an
optional AI assistant built on Google ADK that talks to any OpenAI-compatible LLM gateway (LiteLLM). A separate
**demo vendor back-office** (`vendor_mock/`) simulates a retailer's inventory system, so Sentinel never generates its
own data: it connects to the demo vendor exactly as it would to a real one.

> **New here?** Go to [Quick start](#quick-start), then [Using the app](#using-the-app). For a screen-by-screen walk-through,
> demo scripts and troubleshooting, see **[GUIDE.md](GUIDE.md)**. To see how it works inside, read
> [Algorithms](#algorithms-how-detection-works), [Models used](#models-used) and [How AI helps](#how-ai-helps).

---

## Contents

1. [What it does](#what-it-does)
2. [Quick start](#quick-start)
3. [Using the app](#using-the-app)
4. [Architecture](#architecture)
5. [The data: connectors and the demo vendor](#the-data-connectors-and-the-demo-vendor)
6. [Schedules, SOPs and vendor tasks](#schedules-sops-and-vendor-tasks)
7. [Algorithms: how detection works](#algorithms-how-detection-works)
8. [Models used](#models-used)
9. [How AI helps](#how-ai-helps)
10. [The AI assistant in detail](#the-ai-assistant-in-detail)
11. [Measured results](#measured-results)
12. [Using a model outside the app](#using-a-model-outside-the-app)
13. [Configuration](#configuration)
14. [API](#api)
15. [Testing](#testing)
16. [Project layout](#project-layout)
17. [What is in git and what is not](#what-is-in-git-and-what-is-not)
18. [Running on locked-down Windows](#running-on-locked-down-windows)
19. [Troubleshooting](#troubleshooting)

---

## What it does

| Area | Screens | What you get |
|---|---|---|
| **Executive** (default) | Overview · Alerts · Plan · Story | three headline numbers, where problems happen, the five alerts to work first, a stock-story drawer and an investigator-hours slider, all without statistics vocabulary |
| **Business** | 1 Data → 2 Train → 3 Act | connect a vendor over MCP (or import a CSV), let four methods compete on that vendor's own history, then alerts, a dashboard, an investigation planner, drill-downs with the SOP to follow, and triage |
| **Operations** | Schedules | sync → use or retrain the model of your choice → detect at set times; vendor tasks proposed from the SOPs wait for a person's approval |
| **Analyst** | Models · Experiments | every metric, threshold, signal and run; model export as a Python bundle or ONNX |
| **Assistant** | chat on every page, Assistant page, Settings | a team of AI agents that reads alerts and plans, looks up live stock in the vendor system, quotes the SOPs, sets up schedules and proposes jobs and vendor tasks for you to confirm |
| **How it works** | story + Present mode | a seven-slide leadership story with live figures |

The use case comes from the AI Friday brief, *anomaly detection in inventory*. An unsupervised model flags unusual
patterns (shrinkage, theft, counting errors), alerts warehouse teams, and a dashboard shows anomaly trends by store and
category. Inputs: daily inventory counts, warehouse transaction logs, historical loss-prevention flags, and store and
category details.

---

## Quick start

### Requirements

| Tool | Version | Why |
|---|---|---|
| Python | **3.11 to 3.14** | backend (the start scripts check this and rebuild `.venv` if needed) |
| Node.js | 18+ (LTS recommended) | builds the React UI |
| An LLM gateway | optional | only for the AI assistant; everything else runs offline |

No Docker and no database are needed.

### Start it

```bash
git clone <this repo> inventory_anomaly
cd inventory_anomaly
```

**Windows**: double-click `startup.bat`, or from a terminal:

```bash
startup.bat
```

**macOS / Linux:**

```bash
./start.sh
```

The script:

1. creates `.venv` with a supported Python
2. installs `requirements.txt`
3. runs `npm install` in `frontend/`
4. builds the UI into `frontend/dist`
5. starts the **demo vendor back-office** at **http://127.0.0.1:8020** (a simulated retailer system; its first start
   seeds about 2.7M rows in under a minute) and registers it as Sentinel's connector
6. starts the app at **http://127.0.0.1:8000** and opens your browser

The first run takes a few minutes. Later runs start in seconds.

| Option | Effect |
|---|---|
| `--port 8080` | serve on another port |
| `--no-browser` | do not open a browser tab |
| `--dev` | API with auto-reload on :8000 and the Vite dev server with hot reload on **:5173** |
| `--no-vendor` | do not start the demo vendor (connect your own system on the Data page) |

Other launchers: `run_demo.ps1` (build the UI and serve it, Windows PowerShell) and `dev.ps1` (dev mode: vendor, API and
UI dev server; `-NoVendor` skips the vendor).

### Manual start (any OS)

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm install --prefix frontend
npm run build --prefix frontend
# the demo vendor (optional; any MCP server implementing docs/connector-contract.md works)
.venv/bin/python -m uvicorn vendor_mock.app:app --host 127.0.0.1 --port 8020 &
SENTINEL_DEFAULT_CONNECTOR_URL=http://127.0.0.1:8020/mcp/ \
  .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

(On Windows use `.venv\Scripts\python.exe`.) Serve the API with **one** worker: the scheduler runs inside it.

### Start clean

Stop the app and delete the `data/` folder. It holds every snapshot, model, run, triage decision, connector, schedule
and the assistant settings, and it is recreated empty on the next start. The demo vendor keeps its own data in
`data_vendor/` (or press **Reset demo data** on its dashboard).

---

## Using the app

### Five-minute path

| Step | Where | Do | Takes |
|---|---|---|---|
| 1 | **Overview** (Executive) | press **Run the whole pipeline** on an empty install (sync the vendor, train, detect) | ~1-2 min |
| or 1a | **1 Data** (Analyst) | the demo vendor is already connected: press **Sync now** (120 days x 40 stores x 250 SKUs = 1.2M rows) | ~30 s |
| 1b | **2 Train** | tick the four methods, press **Train**; the best becomes the *model in use* | ~1 min |
| 1c | **3 Act** | press **Run detection** | ~2 min |
| 2 | **Act → Alerts** | open the top critical alert: reasons, money at risk, P(true), **What to do** (the SOP, escalation level, "Raise vendor task", live stock) | |
| 2b | demo vendor **Tasks from Sentinel** (:8020) | close the task with an outcome; the next sync turns it into team feedback | |
| 3 | **Act → Investigation planner** | enter hours (e.g. 120) and hourly cost (e.g. £28) to get a ranked work list per team | instant |
| 4 | **Act → Triage** | **Simulate a week of team reviews**, then **Retrain with feedback** | ~40 s |
| 5 | **Schedules** | **New schedule**: daily at 06:00, retrain Isolation Forest, propose tasks for critical alerts; press **Run now** | ~1 min |
| 6 | demo vendor dashboard | **Close today's trading (+1 day)**, then **Run now** again: only the new day is pulled | |
| 7 | **Chat** (bottom right) | "Why was the top alert flagged?", "What's the SOP?", "Stock of K00012 at S003?" (needs a gateway) | |

### Executive mode vs Analyst mode

The app opens in **Executive mode**:

- **Overview** shows money at risk, alerts worth a visit with their expected return, and how many times better machine
  learning ranks real problems than today's rule.
- **Where it happens** is a store x category heatmap.
- **Work these first** lists the planner's top five alerts.
- **Alerts**, **Plan** and **Story** complete the set.

The **Executive | Analyst** switch (top right) shows every screen. The browser remembers your choice.

### Each screen in one line

| Screen | What it is for |
|---|---|
| **1 Data** | Connect vendors over MCP (URL + token, test, **Sync now**, warnings such as a stale feed), or import a CSV / ZIP; preview a snapshot's daily rows, stores, SKUs, loss-prevention flags and (demo vendor only) the answer key; export a ZIP |
| **2 Train** | Pick methods and settings; see the leaderboard, precision-recall curves and "what the winner catches" by anomaly type |
| **3 Act → Alerts** | Filter and sort alerts; open one for reasons, value at risk, P(true) and triage buttons; CSV download |
| **3 Act → Dashboard** | Trend by severity or type, store x category heatmap, top stores, teams and categories |
| **3 Act → Investigation planner** | Hours and cost in; ranked work list, expected recovery, return on cost, breakeven hours, per-team CSV / ZIP out |
| **3 Act → Drill-down** | One SKU in one store over time: expected against counted stock, daily gap, flagged days and why, and the SOP checklist for the alert |
| **3 Act → Triage & feedback** | Record outcomes, simulate reviews, recalibrate P(true), retrain with a feedback re-ranker |
| **Schedules** | Timed pipelines with the model policy of your choice, run history linked to the alerts, approvals waiting from scheduled runs |
| **Models** | Every model with metrics, thresholds, drivers, calibration; export a bundle or ONNX |
| **Experiments** | Every training run with its leaderboard |
| **Assistant** | Full-page chat, saved conversations, per-agent token usage and cost |
| **Settings (⚙)** | LLM gateway URL, key, model, TLS options, single-agent or team mode, prices |

### Connecting your own inventory system

Sentinel talks to inventory systems through the **Sentinel Inventory Connector** contract: a small set of MCP tools
(capabilities, stores, SKUs, paged daily movements, loss-prevention flags, a live stock lookup, and a task inbox). Put
an MCP adapter in front of your system (see **[docs/connector-contract.md](docs/connector-contract.md)**), then add it on
**1 Data → Connect a data source** with its URL and token. Models always train on **that system's own history**.

### Importing a CSV instead

Upload a CSV with **one row per store, SKU and day**.

- **Required:** `date`, `store`, `sku`, counted closing stock, and either expected closing stock or opening + received + sold.
- **Recognised automatically:** common names such as `site`, `article`, `book_qty`, `soh_counted`, `receipts`, `voids`.
- **Optional columns that sharpen detection:** till scans, keyed-in scans, voids, overrides, after-hours scans, receiving
  scans, returns, promotion flag. A missing column switches off the signals that need it, with a note.
- **Optional ZIP with extra tables:** `stores.csv`, `skus.csv` (`category`, `unit_cost`) and `lp_flags.csv`.
- **Other column names:** map them with a JSON column map, for example `{"counted_closing": "physical_qty"}`.

### Connecting the AI assistant (optional)

1. Open **Settings (⚙)**.
2. Enter the gateway **URL** (e.g. `https://litellm.mycompany.net`) and **API key**, then press **Connect**.
3. Pick a model that supports **tool / function calling**, then press **Test** and **Save**.
4. Open the chat (bottom right on every page) and ask, for example:
   - "Show the top 10 critical alerts"
   - "Why was A000001 flagged?"
   - "Plan 120 investigator hours at £28 an hour"
   - "Did machine learning beat the rule of thumb?"

The key is stored server-side in `data/settings.json` (git-ignored) and is never sent back to the browser.

---

## Architecture

```mermaid
flowchart LR
  subgraph Browser["Browser: React + TypeScript + Recharts"]
    UI["Executive / Business / Analyst pages"]
    Chat["Chat dock + voice input"]
  end

  subgraph API["FastAPI (one process, port 8000)"]
    R["REST routers<br/>connectors, datasets, training, runs,<br/>planner + triage, schedules, SOPs, jobs, settings"]
    J["Background job queue<br/>(progress, cancel)"]
    SC["Scheduler<br/>(timed pipelines)"]
    subgraph ML["ML services"]
      SY["sync: MCP client,<br/>local copy, snapshots"]
      FE["features: 16 signals"]
      DT["detectors: z-score, IForest,<br/>LOF, autoencoder"]
      CA["calibration: P(true)"]
      DE["detection: alerts + reasons"]
      PL["planner: work lists"]
      RR["reranker: LightGBM on feedback"]
      EX["model_export: bundle + ONNX"]
    end
    subgraph AI["Assistant"]
      ADK["Google ADK agent team"]
      TL["32 tools"]
      KB["BM25 doc search"]
      MCP["MCP server /mcp/"]
    end
  end

  Store[("data/<br/>.npy column store,<br/>models, runs, triage")]
  GW["LLM gateway (LiteLLM,<br/>OpenAI-compatible)"]
  Ext["External agents<br/>(Claude Desktop, IDEs)"]
  Vendor["Vendor inventory system<br/>(MCP connector; demo: vendor_mock :8020)"]

  UI --> R --> J --> ML --> Store
  SC --> J
  SY <-- "MCP: data in, approved tasks out" --> Vendor
  Chat -- SSE --> ADK --> TL --> ML
  ADK <--> GW
  Ext <--> MCP --> TL
```

- **No database.** Each dataset is a folder of memory-mapped `.npy` columns (`colstore.py`), so 5M rows load instantly
  and stay off the heap. Models are `joblib` pipelines plus a JSON metadata file. Runs are `.npy` score arrays plus an
  incidents CSV. Triage decisions are append-only JSONL.
- **Long work runs as jobs.** Endpoints return `202` with a job id; the UI polls `/api/jobs/{id}` for steps, progress
  and estimated time, and can cancel.
- **The UI is served by the API.** In production mode FastAPI serves `frontend/dist`, so it is a single process on a
  single port (plus the demo vendor, a separate process, when you use it).
- **Sentinel is an MCP client and an MCP server.** It reads vendors through MCP connectors (`services/connectors.py`,
  `services/sync.py`) and exposes its own tools to external agents at `/mcp/`. `app/mcp_compat.py` bridges the mcp 1.x
  and 2.x SDKs.

---

## The data: connectors and the demo vendor

### Where the data comes from

Sentinel does not make up data. Each **connector** is a vendor's MCP server implementing the
[connector contract](docs/connector-contract.md). A **sync** (`services/sync.py`, a background job):

1. checks the vendor's capabilities (contract version, status, fields, task types);
2. pulls stores, SKUs and **only new days** of stock movements, plus `resync_days` (3) of recent days for late
   corrections. Pages are columnar and dictionary-encoded, 50,000 rows each, and go into a local copy under
   `data/connectors/<id>/mirror/`. A first full pull of 1.2M rows takes about 25 s on a laptop;
3. pulls loss-prevention flags, and the answer key **only if** the vendor is a demo that offers one;
4. reads back the outcomes of vendor tasks Sentinel raised (they become team feedback);
5. builds a **snapshot** dataset of the last `window_days` (120) and keeps the newest `retention` (3) snapshots. It
   never deletes the training data of the model in use, of a schedule's fixed model, or of a running job;
6. warns about a stale feed (no new trading day), missing days or a short last day.

Team decisions are stored **per connector**, so they carry over from one snapshot to the next.

**Why train on each vendor's own data?** The detectors are unsupervised: they learn what normal looks like for *these*
stores (delivery days, count noise, till habits, promotions). A model trained on another estate would flag that
estate's normal as anomalous. The same pipeline therefore runs against the demo vendor and a real one.

Each daily row is one SKU in one store: opening stock, received, sold, returned, transfers in and out, adjustments,
expected and counted closing stock, till scans, keyed-in scans, voids, overrides, after-hours scans, receiving scans and
a promotion flag. Only counted stock and expected (or opening + sold) stock are required.

### The demo vendor back-office (`vendor_mock/`)

A separate FastAPI app (port 8020) that plays a retailer's inventory system:

- **Its own SQLite database** in `data_vendor/`, seeded on first start with 40 stores x 250 SKUs x 270 days (150 past,
  120 future). Size it with `VENDOR_MOCK_STORES`, `VENDOR_MOCK_SKUS`, `VENDOR_MOCK_HISTORY_DAYS` and
  `VENDOR_MOCK_FUTURE_DAYS`.
- **A business clock.** Only days up to yesterday are visible. The clock follows the calendar, and
  **Close today's trading (+1 day)** fast-forwards it, so new data arrives day by day for the scheduler.
- **A back-office UI:** dashboard, stores, products, stock ledger, loss-prevention flags, a **Tasks from Sentinel**
  inbox where store staff set the status and outcome, and a demo answer-key page.
- **The MCP server** at `/mcp/` (optional bearer token: `VENDOR_MOCK_TOKEN`) implementing the connector contract.

Its simulator (`vendor_mock/sim/synth.py`) gives each series (one SKU in one store) two stocks:

- a **physical stock** that the business cannot see
- a **book stock** that the system computes from deliveries, sales, returns, transfers and adjustments

Every evening the stock is counted (RFID-style) and the count resets the book. The daily gap
`expected_closing - counted_closing` is therefore the core shrinkage signal.

- **Stores** span six regions across the UK and Ireland in four formats (high street, retail park, flagship, outlet),
  each with a warehouse team.
- **SKUs** fall into eight fashion and home categories, with realistic unit costs.

**Seven injected problem types**, each with its own fingerprint:

| Type | What happens | Fingerprint the models can see |
|---|---|---|
| External theft | stock goes missing for several days, more on high-risk items and hotspot stores | 7-day shrink well above count noise |
| Internal theft | 3 to 8 items go missing in one store on the same night | after-hours scans, store-wide shrink that day |
| Till / scan fraud | sweethearting (voids, overrides, keyed-in items) or refund fraud | till behaviour against the store's habit, returns |
| Counting error | a miscount that the next count reverses | today's gap reverses yesterday's |
| Receiving error | a delivery booked at a different quantity from what arrived | booked against scanned at receiving |
| Data-entry error | a quantity typed ten times too large, or with the wrong sign | delivery or adjustment many times the usual size |
| Sales pattern change | phantom stock (no sales while the books show stock) or an unexplained spike | sales against the promotion-adjusted normal, zero-sales runs |

**Hard negatives:** promotions, delivery-day noise, new lines, count noise that grows with stock and small background
shrink. They make a naive rule raise false alarms that the learned methods learn to ignore.

**Loss-prevention flags** are partial and noisy, as in real life:

- 40% of thefts and 20% of other problems are ever flagged
- 10% of flags carry the wrong type
- a few flags land on ordinary days
- each flag is reported 2 to 10 days after the day it concerns

**The answer key** (`truth_type`, `truth_incident`, `truth_loss_units`) stays inside the demo vendor and is offered
through a demo-only tool. Sentinel uses it **only** to mark the methods' homework and to simulate team reviews. It is
**never a model input**, and real vendors have none: there, models are judged on loss-prevention flags and team feedback.

---

## Schedules, SOPs and vendor tasks

### Schedules (`services/scheduler.py`, page **Schedules**)

A schedule says **when** (every day / some weekdays at HH:MM, or every N hours, in a time zone), **which data** (sync a
connector first, or score its latest snapshot) and **which model**:

| Model policy | What it does | When to use |
|---|---|---|
| **The model in use** | scores with whatever model is active when the run starts | you manage models by hand on the Models page |
| **A specific saved model** | always the same model | stable, comparable scores run to run |
| **Retrain each run** | trains the algorithms you pick (z-score, Isolation Forest, autoencoder, LOF, with their settings) on the fresh snapshot and scores with the best; optionally "at most every N days" and "make it the model in use" | follow drift: new lines, seasons |

Each run is **one pipeline job** (sync, then train, then detect, then propose) on the shared queue. It cancels as a
unit and never overlaps itself. A daemon thread checks every 30 s. A run missed while Sentinel was down becomes one
**catch-up** run (or is skipped, per schedule), and a run left half-finished by a restart is marked failed. History is
kept in `data/schedule_runs.jsonl`. Each run records new alerts (those reaching into days the previous run had not
seen), critical alerts, value at risk and any error, with its **error kind** and the SOP to follow.

With **Propose vendor tasks** on, a run picks new alerts at the chosen severities (and minimum £), up to N, and creates
**one proposal** using each alert's SOP. Nothing goes to the vendor until someone presses **Approve and raise** on the
Schedules page (or in the chat). Proposals from scheduled runs wait **72 hours**.

### SOPs (`docs/sops/*.md`, `services/sops.py`)

Standard operating procedures for what to do when stock goes missing, as Markdown with YAML front matter (schema in
[docs/sops/README.md](docs/sops/README.md)):

- **`missing-inventory-response`** is the master procedure: triage, an **escalation matrix** (severity x value at risk
  → L1 store check 72 h, L2 store manager + loss prevention 24 h, L3 regional loss prevention 4 h), evidence rules,
  closure and feedback;
- one SOP per alert type (external theft, internal involvement handled confidentially, till fraud, counting error,
  receiving error, data-entry error, sales stopped or spiked, unclear);
- **`data-feed-failure`** for failed or stale syncs and scheduled runs, and **`false-positive-handling`**.

The alert detail and the drill-down show the matching SOP as a checklist, with steps filled in from the alert, owners,
deadlines and evidence. A step with a task template offers **Raise vendor task**, and a **live stock** check reads the
vendor system now. The assistant quotes SOPs (`get_sop`, `find_sop`), and MCP clients read them as `sentinel://sop/<id>`.

### Vendor tasks (`services/vendor_tasks.py`)

Approved tasks go to the vendor's `create_task` tool, with an idempotency key `<alert_key>:<type>` so that retries never
duplicate work. Every sync reads status changes back. A **closed task becomes a team decision** for the alert:
confirmed loss → confirmed theft (theft-type alerts) or process issue, count corrected → counting error, process fixed →
process issue, no issue → false alarm. Those decisions feed P(true) recalibration and the feedback re-ranker.

---

## Algorithms: how detection works

The pipeline end to end:

```
daily rows ──► 16 detection signals ──► 4 unsupervised detectors ──► score ──► percentile ──► severity
                                                                                  │
                                    P(true) calibration ◄─────────────────────────┤
                                                                                  ▼
      planner (expected £ per investigator hour) ◄── alerts (flagged days grouped) + reasons + likely type
                                                                                  │
            feedback re-ranker (LightGBM) ◄── team triage decisions ◄─────────────┘
```

### 1. Feature engineering: 16 "quiet on ordinary days" signals (`services/features.py`)

All features are computed with **segment-aware cumulative sums** over rows sorted by (store, SKU, date). This avoids a
pandas groupby and handles 5M rows in seconds. Trailing windows exclude the current day, so each day is compared with
its own recent past.

Each signal is scaled so that **ordinary days have light tails**, using Poisson or binomial z-scores against each
store's own habits, with variance normalised by the series' own count noise. This is the main reason the learned
methods beat the rule of thumb.

| Signal | Definition (simplified) | Catches |
|---|---|---|
| `shrinkage_pct` | (expected − counted) / expected x 100 | any loss |
| `variance_z_series` | (gap − 28-day mean gap) / max(28-day std, 0.35 + 2.5% of stock) | gaps beyond this item's own noise |
| `shrink_sum_7_z` | 7-day summed gap / count noise (miscounts cancel over a window; real loss does not) | slow, persistent theft |
| `shrink_pct_7` | 7-day gap / (7-day sales + stock) | persistent theft |
| `reversal_index` | √(−yesterday's gap x today's gap) / noise | miscounts reversed the next day |
| `velocity_z` | (sold − promotion-adjusted 28-day baseline) / √expected | sales spikes and drops |
| `zero_sales_streak` | run length x baseline daily sales (expected units missed) | phantom stock |
| `receiving_gap_units` | units booked − units scanned at receiving | receiving errors |
| `received_vs_typical` | delivery size / typical delivery for the item | data-entry errors (x10) |
| `adjustment_vs_typical` | adjustment size / 28-day typical | data-entry errors |
| `returns_z` | returns against the expected return rate | refund fraud |
| `manual_entry_z` | keyed-in scans vs the store's rate (binomial z) | sweethearting |
| `void_z` | voided lines vs the store's rate (Poisson z) | till fraud |
| `override_z` | price or quantity overrides vs the store's rate | till fraud |
| `after_hours_z` | scans outside opening hours vs the store's habit | internal theft |
| `store_day_shrink_z` | robust z of the store's total £ shrink that day vs its other days | internal theft (many SKUs at once) |

**Context features** describe the day but do not drive scoring. They are used for explanations and the drill-down:
units and £ variance, units sold, stock cover, delivery day, promotion, unit cost, day of week and category.

### 2. The four detectors (`services/detectors.py`, `services/registry.py`)

All four are **unsupervised**: they learn what a normal day looks like and need no labels. Each is a scikit-learn
`Pipeline` (a `pre` column step, then the `model`) with the same contract: `fit(X)` and `anomaly_score(X)`, where higher
means more unusual.

| Method | How it works | Input | Default settings | Score |
|---|---|---|---|---|
| **Rule of thumb** (robust z-score) *the baseline* | per category, the median and MAD (x 1.4826) of shrinkage % and gap units | 3 baseline columns | MAD floor 0.5 | max \|robust z\| of the two |
| **Isolation Forest** | random trees split the data at random thresholds; unusual days are isolated in few splits | 16 signals, unscaled | 150 trees, 2,048 rows per tree | 2^(−E[path length] / c(ψ)) |
| **Local Outlier Factor** | compares the density of a day's k-neighbourhood with its neighbours' densities (novelty mode against a reference sample of normal history) | 16 signals, standardised | k = 20, 4,000 reference rows | LOF ratio |
| **Autoencoder** | a small neural network (scikit-learn `MLPRegressor`) squeezes each day through a bottleneck and rebuilds it | 16 signals, standardised | layers 16-4-16, ReLU, L2 1e-4, batch 512, lr 1e-3, ≤ 60 epochs, early stopping | mean squared reconstruction error |

Every setting can be changed on the Train page. **Isolation Forest** and **LOF** fall back to built-in pure-numpy
implementations (`np_engines.py`) when scikit-learn's compiled modules are blocked (see
[locked-down Windows](#running-on-locked-down-windows)). They are the same algorithms from the original papers and rank
rows the same way.

### 3. Training protocol (`services/training.py`)

1. **Split by time.** The first 72% of days are history; the **last 28% are the exam**, which is never seen in training.
2. **Sample.** Fit on 200,000 random history rows (100,000 in quick mode). Days with loss-prevention flags are excluded
   by default, so the models learn "normal".
3. **Set thresholds** from the distribution of training scores (about 260 quantile levels, dense in the tail):
   - **alert** = the (1 − alert rate) quantile; the default alert rate is 0.8%, so the 99.2nd percentile
   - **high** = the 99.8th percentile
   - **critical** = the 99.95th percentile
4. **Mark the exam.** Use every positive in the exam window plus 300,000 sampled negatives, weighted so they stand for
   all negatives. Labels come from a demo vendor's answer key; on real data they come from loss-prevention flags, a lower
   bound because most incidents are never flagged. With no labels, only the alert rate is reported.
5. **Pick the winner.** The method with the highest **average precision** becomes the *model in use*.

| Metric | Meaning |
|---|---|
| **Average precision** (decides the winner) | how well the ranking puts real problems first; 1.0 is perfect, random equals the base rate |
| **Real in the top 1,000** (precision@1000) | of the 1,000 most unusual exam days, how many were real |
| **Incidents caught** | share of hidden incidents with at least one flagged day |
| **Value caught** | share of the £ lost in hidden incidents that falls on flagged days |
| **Detection by type** | incidents caught per anomaly type |
| ROC-AUC, LP recall | also reported, for analysts |

**Drivers** (feature importance) are the mean robust deviation of each signal on flagged exam days, normalised to sum
to 1. This works the same way for every method, including the ones without built-in importances.

### 4. P(true): calibrating scores into probabilities (`services/calibration.py`)

A score percentile is not a probability, so each model learns **P(real problem | score percentile)**:

- 16 bins above the alert threshold, spaced geometrically so they get denser towards the top
- the rate of real problems in each bin, smoothed with a **Beta(1, 1) prior** (Laplace smoothing)
- made monotone (a higher score never means a lower probability) with **weighted pool-adjacent-violators** isotonic
  regression, implemented in pure numpy

Before any labels exist, a stated prior is used: 15% of alerts at the threshold are real, rising to 60% at the very top.
**Recalibrate P(true)** on the Triage tab refits the curve from team decisions.

### 5. From flagged days to alerts (`services/detection.py`, `services/explain.py`)

Detection scores every row in 250k-row chunks, maps scores to percentiles, and marks medium, high or critical severity.
Then:

- **Grouping.** Flagged days of the same SKU in the same store become one **alert (incident)**. A single quiet day
  between flagged days is bridged.
- **Value at risk** = Σ max(gap, 0) x unit cost over the alert's days.
- **Peak day** = the day with the highest score. Its signals drive the reasons and the type guess.
- **Reasons.** Each signal's robust deviation from the training baseline for that **category** (median, MAD, 99th
  percentile) is ranked. The top three with deviation ≥ 2 become plain sentences, such as *"Delivery booked as 240 units
  but 24 were scanned in"*. Three variants of the same shrinkage story are collapsed into one.
- **Likely type.** Ordered rules over the peak day, each with a confidence:

  | Order | Rule | Likely type |
  |---|---|---|
  | 1 | delivery or adjustment about 5x or more its typical size | data-entry error |
  | 2 | reversal ≥ 3, or a short net-zero swing | counting error |
  | 3 | delivery day with a booked-vs-scanned gap | receiving error |
  | 4 | voids, overrides, keyed-in items or returns z ≥ 3 | till / scan fraud |
  | 5 | after-hours scans or store-wide shrink z ≥ 3 | internal theft |
  | 6 | big sales shift or zero-sales run with little net loss | sales pattern change |
  | 7 | 7-day shrink z ≥ 3, or sustained net loss | external theft |
  | 8 | otherwise | unclear |

- **P(true)** for each alert comes from the calibration curve at its peak percentile.

### 6. Investigation planner (`services/planner.py`)

The planner turns investigator hours into a ranked work list. For each open alert *i*:

```
cash_i  = value_at_risk_i x cash_share(type_i)          # book-keeping errors are corrected, not recovered as money
V_i     = cash_i x recovery_rate                         # recovered now (default 40%)
        + cash_i x persist(type_i) x horizon_days / 28   # similar loss prevented from recurring
EV_i    = P(true)_i x V_i                                # expected value
cost_i  = minutes(type_i) / 60 x hourly_cost             # e.g. theft 60-90 min, data-entry error 10 min
```

Alerts are sorted by **EV per investigator hour** and taken greedily until the hours run out. The planner reports:

- expected recovery, cost and return on cost
- **breakeven hours**: the point where the next alert returns less than it costs
- a curve of what more hours would buy
- a comparison against the naive approach of working down by raw £ at risk

Work lists come out as one CSV per warehouse team. All figures are **estimates** that depend on the recovery rate and
on P(true).

### 7. Learning from feedback (`services/triage.py`, `services/reranker.py`)

Teams record one of four outcomes per alert: **confirmed theft, counting error, process issue or false alarm**.
Decisions are stored per connector (per dataset for imports) under a stable alert key, so they carry across detection
runs and snapshots. Closed vendor tasks arrive as decisions by themselves. With the demo vendor,
**Simulate a week of team reviews** fills in decisions from its answer key, with noise. Teams work the top of the queue
and spot-check further down.

**Retrain with feedback** becomes available after 30 reviews with at least 5 real problems and 5 false alarms. It trains
a supervised **re-ranker** on top of the unsupervised detector:

- **Features:** all 25 features plus the base detector's percentile.
- **Labels and weights:**
  - confirmed alert days: positive, weight 1
  - historical loss-prevention-flagged days: positive, weight 0.7
  - false alarms: negative, weight 1
  - 20,000 unlabelled days: negative, weight 0.2
- **Classifier:** **LightGBM** (200 trees, 15 leaves, learning rate 0.05, row and column subsampling 0.8). It falls back
  to logistic regression if LightGBM cannot load.
- **Score:** `α x base percentile + (1 − α) x P(real)`, with α = 0.4 by default.
- **Judged honestly:** only on exam days that **nobody reviewed**, shown as a before/after table, so it cannot win by
  memorising the labels it was given.

---

## Models used

### Machine-learning models (run locally, inside the app)

| Model | Library | Kind | Role |
|---|---|---|---|
| Robust z-score rule | numpy | statistical rule | baseline, today's typical shrinkage rule |
| Isolation Forest | scikit-learn `IsolationForest` (or built-in numpy engine) | unsupervised tree ensemble | usually the winner |
| Local Outlier Factor | scikit-learn `LocalOutlierFactor` (or built-in numpy engine) | unsupervised density / neighbours | competitor |
| Autoencoder | scikit-learn `MLPRegressor` | unsupervised neural network | competitor |
| Feedback re-ranker | **LightGBM** `LGBMClassifier` (fallback: scikit-learn `LogisticRegression`) | supervised gradient boosting | learns from team decisions |
| P(true) calibration | numpy (Beta prior + isotonic PAV) | probability calibration | turns scores into "8 in 10 alerts like this are real" |
| Exported models | `onnx` graph + `onnxruntime` validation | inference format | use the model outside Python |

All of these train on your machine, on your data. Nothing is sent anywhere.

### Language model (optional, for the assistant only)

| Item | Detail |
|---|---|
| Provider | **any** OpenAI-compatible gateway, typically a [LiteLLM](https://docs.litellm.ai/) proxy; you choose it in Settings |
| Model | whichever model you pick from the gateway's list; it **must support tool / function calling** (e.g. a Claude, GPT or Gemini model exposed by the gateway). No model is bundled or hard-coded |
| How it is called | Google ADK `LiteLlm` adapter → `openai/<model>` at `<gateway>/v1`, temperature 0.2, 120 s timeout |
| Agent framework | **Google ADK** (`google-adk`): `LlmAgent` tree, `Runner`, `DatabaseSessionService` (SQLite) |
| Docs search | **BM25** over README, GUIDE and the story (no embeddings, no vector DB) |
| Voice input | the browser's built-in Web Speech API (speech-to-text happens in the browser) |

---

## How AI helps

There are two kinds of AI in Inventory Sentinel, and they do different jobs.

### 1. Machine learning finds the problems

| Without it (today's rule) | With it |
|---|---|
| A fixed shrinkage threshold flags any big one-day gap, including promotions, delivery-day noise and miscounts that reverse the next day | Signals are scaled to each item's and store's own normal, so ordinary noise stays quiet |
| It only sees shrinkage | It combines 16 signals: till behaviour, receiving scans, after-hours activity, sales velocity, store-wide patterns |
| It misses till fraud and internal theft, which never show up as one big gap | Isolation Forest catches almost all till fraud and internal theft |
| It ranks real problems poorly | **1.7x the average precision**; **986 of the top 1,000** exam days are real problems vs 426 for the rule |
| Every alert looks equally urgent | Each alert carries money at risk, a likely type, plain reasons and P(true) |
| Investigator time goes to the biggest £ figure | The planner spends hours where **expected recovery per hour** is highest |
| The rule never improves | Team decisions train a re-ranker, judged on days nobody reviewed |

The learned methods need **no labels**. They learn what normal looks like, which matters because real
loss-prevention flags cover only a fraction of incidents.

### 2. A language model makes the results easy to use

The assistant is a team of agents that lets anyone, from a store manager to a CIO, ask questions in plain English
instead of learning the screens:

- **Answers from live data.** "Why was A000123 flagged?", "Which stores lose most in beauty?", "What does 120 hours
  buy us?". Every number comes from a tool call against the app; the assistant is told never to invent figures.
- **Knows what you are looking at.** "Why was *this* flagged?" works on the alert open on screen.
- **Explains the maths.** "What does average precision mean?", "Why did Isolation Forest win?" (glossary plus BM25 doc
  search over this README and the guide).
- **Drafts actions, you decide.** "Train all four methods" or "run detection" become a **proposal card** you confirm.
  The assistant never runs or changes anything by itself.
- **Speaks the audience's language.** In Executive mode it answers in under 90 words without statistics jargon.
- **Responsible by design.** It describes patterns as "consistent with" theft or error, never accuses a person or team
  (the data holds no employee identities), labels figures that come from a demo vendor's answer key, and follows the SOPs
  rather than improvising procedures.
- **Open to other agents.** The same 32 tools are an **MCP server**, so Claude Desktop, IDE agents or other apps can
  query alerts and plans directly.

**What the LLM does not do:** it does not score rows, choose alerts, set thresholds or compute money figures. All of
that is deterministic, reproducible ML and arithmetic in the backend. The LLM only reads tool results and explains them.

---

## The AI assistant in detail

### Agent team (`assistant/agents.py`)

A **front-door agent** answers quick questions itself and hands deeper ones to a specialist (Google ADK `sub_agents`
with transfer):

| Agent | Handles | Tools |
|---|---|---|
| **Front door** (`sentinel_assistant`) | greetings, "what is loaded", status, routing | common: `app_state`, `search_docs`, `explain_metric`, `job_status`, `usage_summary` |
| **Data analyst** | snapshots and imports, columns, LP flags, live stock lookups; proposes sync / re-map | common + `list_datasets`, `describe_dataset`, `preview_rows`, `list_connectors`, `vendor_lookup`, `propose_job` |
| **Model analyst** | methods, metrics, drivers, training, feedback retraining, ONNX, model in use | common + `available_algorithms`, `list_models`, `model_detail`, `list_experiments`, `triage_summary`, `list_datasets`, `propose_job` |
| **Alert investigator** | runs, alerts, why something was flagged, drill-downs, the SOP to follow, live stock, trends, hotspots | common + `list_detection_runs`, `alert_summary`, `list_alerts`, `explain_alert`, `sku_drilldown`, `anomaly_trend`, `hotspots`, `search_series`, `get_sop`, `find_sop`, `vendor_lookup`, `list_vendor_tasks`, `propose_job` |
| **Loss-prevention planner** | investigator hours, expected recovery, ROI, work lists, escalation | common + `list_detection_runs`, `alert_summary`, `investigation_plan`, `compare_plans`, `hotspots`, `get_sop`, `find_sop` |
| **Operations coordinator** | connectors and syncs, schedules (create, change, run, history), vendor tasks, SOPs for missing stock and failed feeds | common + `list_connectors`, `connector_status`, `vendor_lookup`, `list_vendor_tasks`, `list_schedules`, `schedule_history`, `get_sop`, `find_sop`, `list_detection_runs`, `list_alerts`, `list_models`, `available_algorithms`, `propose_job` |
| **Explainer** | how the app works, glossary, screens, troubleshooting | common |

Settings can switch to **single-agent mode**: one agent with every tool, which is cheaper on small models.

### What each agent sees

Every agent's instruction is rebuilt on each turn from three parts:

1. **Preamble:** what the app is and its conventions (British English, £, plain metric wording).
2. **Guardrails:** ten rules, summarised below.
3. **Current state** (`context_pack.py`): the page, tab and mode you are on, the selected dataset, run, alert and
   store/SKU, the model in use, connectors (last sync, warnings, open vendor tasks), schedules (next run, last result),
   approvals waiting from scheduled runs, running jobs and pending proposals. Tokens are never included.

Tool arguments such as `run_id`, `alert_id` and `store_id` are filled from the UI selection when the model leaves them
empty (`adk_tools.py`). Tool results are capped at 20 rows and 600-character texts to keep prompts small.

**Guardrails (summary):**

- never invent numbers
- one well-chosen tool call, then answer
- every change is a proposal for you to confirm (syncs, schedules and vendor tasks included)
- planner figures are estimates
- uploads, deletes and triage happen in the app's pages, not in chat
- say which model produced a run
- "consistent with", never accusations
- name figures that come from a demo vendor's answer key
- live vendor lookups are quoted as live, with their as-of date; procedures come from the SOPs, never improvised
- executive answers stay short and jargon-free

### The 32 tools (`assistant/tools.py`)

| Group | Tools |
|---|---|
| Data | `list_datasets`, `describe_dataset`, `preview_rows` |
| Vendor | `list_connectors`, `connector_status`, `vendor_lookup` (live), `list_vendor_tasks` |
| Operations | `list_schedules`, `schedule_history`, `get_sop`, `find_sop` |
| Models | `available_algorithms`, `list_models`, `model_detail`, `list_experiments` |
| Alerts | `list_detection_runs`, `alert_summary`, `anomaly_trend`, `hotspots`, `list_alerts`, `explain_alert`, `sku_drilldown`, `search_series` |
| Planning | `investigation_plan`, `compare_plans`, `triage_summary` |
| Jobs | `propose_job`, `job_status` |
| Help | `search_docs`, `explain_metric`, `app_state`, `usage_summary` |

### Proposals, not actions (`assistant/proposals.py`)

There are twelve proposal kinds:

- jobs: `sync`, `configure`, `train`, `detect`, `retrain_feedback`, `export_dataset`, `export_onnx`, `run_schedule`
- changes applied on confirmation: `activate_model`, `create_schedule`, `update_schedule`, `vendor_task`

The assistant validates the parameters, estimates the run time and shows a card. Nothing runs until you press
**Confirm**; then jobs go through the normal job queue. Chat proposals expire after 30 minutes. Vendor-task proposals
from scheduled runs wait 72 hours on the Schedules page. Schedule proposals accept chat-friendly shortcuts such as
`{"at": "06:00", "days": ["mon", "thu"], "models": ["iforest"], "auto_tasks": true}`.

### Transparency and cost (`assistant/usage.py`)

- **Thinking trail.** Every answer shows hand-overs between agents, tool calls with timings, and the tokens and cost
  of that answer.
- **Usage page.** The Assistant page breaks usage down by agent and by day.
- **Prices.** Prices come from your Settings override, then the gateway's own price list, then LiteLLM's bundled price
  map; otherwise cost shows as "n/a".
- **Limits.** Each turn is capped at 24 LLM calls and a 120 s timeout.
- **Saved conversations.** Conversations are kept in `data/assistant.sqlite`.

### What leaves your machine

Only when a gateway is configured, and only to that gateway:

- the conversation
- the current-state summary
- tool results: aggregates and at most 20 rows per call

Raw datasets, models and the answer key are never uploaded. Without a gateway, nothing leaves the machine.

### MCP server for external agents (`assistant/mcp_server.py`)

`http://127.0.0.1:8000/mcp/` exposes the 32 tools over streamable HTTP, plus resources: `sentinel://guide`,
`sentinel://readme`, `sentinel://glossary`, `sentinel://story`, `sentinel://sops` and `sentinel://sop/<id>`. Point any
MCP client at that URL. Jobs proposed over MCP still need confirmation in the app. Tools run in a worker thread, so a
live vendor lookup made from an MCP client does not block the server.

---

## Measured results

These figures were measured on 5,000,000 simulated store-SKU-days (80 stores x 500 SKUs x 125 days) on a 6-core laptop.
Four methods were trained on a 200,000-day sample of the history window and marked on the last 28% of days (the exam)
against the simulator's answer key. The default demo vendor is smaller (1.2M rows per 120-day snapshot).

| Method | Average precision | Real in the top 1,000 | Incidents caught | Value caught |
|---|---|---|---|---|
| Rule of thumb (baseline) | 0.25 | 426 | 61% | 50% |
| **Isolation Forest** (winner) | **0.42** (1.7x) | **986** | 55% | **59%** |
| Local Outlier Factor | 0.32 | 583 | 55% | 57% |
| Autoencoder | 0.20 | 374 | 50% | 40% |

- The rule of thumb catches big one-day gaps (miscounts, typing errors) but misses patterns spread across signals.
  Isolation Forest finds almost all till fraud and internal theft, which never show up as one big shrinkage day.
- After a simulated week of team reviews, the **feedback re-ranker** improves on days nobody reviewed (Triage tab).

| Step | Time |
|---|---|
| First sync of 1.2M rows over MCP (pull, snapshot, features, stats) | ~28 s |
| Incremental sync (new day + 3 days of corrections) | ~4 s |
| Train all four methods | ~58 s |
| Detect with Isolation Forest (numpy engine) | ~2 min |
| ONNX export + validation, per model | < 1 s |

---

## Using a model outside the app

On **Models**, open **Use this model elsewhere**.

The **model bundle (.zip)** contains:

- `model.joblib` and `model.json`
- `features.py`, `detectors.py` and `np_engines.py`
- `predict.py`
- pinned `requirements.txt`

Score a file with:

```bash
python predict.py daily.csv scored.csv --skus skus.csv
```

This adds `anomaly_score`, `percentile`, `severity` and `is_alert` to every row.

**ONNX:**

- one float32 input `features` and one output `anomaly_score`
- built directly with the `onnx` package (no skl2onnx)
- validated with onnxruntime to rank 2,000 sample days exactly like the Python model
- runs from C#, Java, JavaScript or anything else with onnxruntime

The feedback re-ranker chains two models, so it is bundle-only.

---

## Configuration

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SENTINEL_DATA_DIR` | `./data` | where datasets, models, runs and settings live |
| `SENTINEL_DEFAULT_CONNECTOR_URL` | unset (the start scripts set it to the demo vendor) | registered as a connector on start-up when there is none |
| `SENTINEL_DEFAULT_CONNECTOR_NAME` / `_TOKEN` | "Demo vendor (simulated)" / none | name and token for that connector |
| `SENTINEL_SCHEDULER` | `on` | `off` disables the scheduler thread (e.g. for a second API process) |
| `VENDOR_MOCK_*` | see [the demo vendor](#the-demo-vendor-back-office-vendor_mock) | demo vendor size, seed, port URL, token, data dir |
| `LITELLM_SSL_VERIFY` | unset (off) | `true` verifies the gateway's TLS certificate |
| `LITELLM_CA_BUNDLE` / `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` | unset | PEM bundle for a corporate CA |
| `LITELLM_LOCAL_MODEL_COST_MAP`, `LITELLM_TELEMETRY`, `ADK_DISABLE_TELEMETRY` | set by the start scripts | offline price map, telemetry off |

### Tunables (`backend/app/config.py`)

| Setting | Default | Meaning |
|---|---|---|
| `MAX_ROWS` | 10M | largest dataset |
| `SYNC_WINDOW_DAYS / SYNC_RESYNC_DAYS / CONNECTOR_RETENTION` | 120 / 3 / 3 | connector defaults (each connector can override) |
| `SYNC_PAGE_SIZE`, `MCP_CALL_TIMEOUT_S` | 50,000, 120 | vendor paging and timeouts |
| `SCHEDULER_TICK_S`, `SCHEDULER_PROPOSAL_TTL_S` | 30, 72 h | scheduler cadence, approval window for its proposals |
| `DEFAULT_TRAIN_SAMPLE` | 200,000 | rows used to fit each method |
| `DEFAULT_ALERT_RATE` | 0.008 | share of training days above the alert threshold |
| `SEVERITY_QUANTILES` | high 0.998, critical 0.9995 | severity cut-offs |
| `TEST_WINDOW_SHARE` | 0.28 | last share of days held out as the exam |
| `PLANNER_DEFAULTS` | 120 h, £28/h, 40% recovery, 28-day horizon | planner inputs |
| `MINUTES_BY_TYPE`, `PERSIST_BY_TYPE`, `CASH_SHARE_BY_TYPE` | per anomaly type | planner assumptions |
| `RETRAIN_MIN_REVIEWED / _EACH` | 30 / 5 | feedback needed before retraining |
| `ASSISTANT_MAX_LLM_CALLS`, `ASSISTANT_TIMEOUT_S` | 24, 120 | assistant limits |

---

## API

Interactive docs are at **http://127.0.0.1:8000/docs**. Heavy endpoints return `202` with a job; poll
`GET /api/jobs/{id}`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/config`, `/api/overview` | versions and engines, limits, summary |
| GET / POST / PUT / DELETE | `/api/connectors`, `/test`, `/{id}/test`, `/{id}/sync`, `/{id}/lookup?store_id=&sku_id=`, `/{id}/tasks` | vendor connectors |
| POST / GET | `/api/datasets/upload`, `/{id}/configure`, `/{id}/preview?table=`, `/{id}/export` | data |
| GET / POST / PUT / DELETE | `/api/schedules`, `/preview`, `/status`, `/runs`, `/pending-approvals`, `/{id}/run`, `/{id}/runs`, `/{id}/enabled` | schedules |
| GET / POST | `/api/sops`, `/api/sops/{id}`, `/api/runs/{run_id}/alerts/{alert_id}/sop`, `/api/vendor-tasks` | SOPs and vendor tasks |
| GET / POST | `/api/models/available`, `/api/train`, `/api/models`, `/api/models/{id}/activate`, `/api/experiments` | training |
| POST / GET | `/api/detect`, `/api/runs`, `/api/runs/{id}/dashboard`, `/alerts`, `/alerts/{alert_id}`, `/series`, `/search` | detection |
| POST / GET | `/api/plan`, `/api/plan/{run_id}/worklist.csv`, `/worklist.zip` | investigation planner |
| POST / GET | `/api/triage`, `/triage/bulk`, `/triage/summary`, `/triage/simulate`, `/api/runs/{id}/recalibrate`, `/api/models/{id}/retrain-feedback` | feedback |
| GET / POST | `/api/models/{id}/export`, `/api/models/{id}/export/onnx`, `/api/models/{id}/onnx/download` | export |
| GET / PUT / POST | `/api/settings/llm`, `/api/assistant/chat` (SSE), `/api/assistant/usage` | assistant |
| MCP | `/mcp/` | 32 tools + resources (guide, readme, glossary, story, SOPs) |

---

## Testing

The smoke tests are plain scripts with no test framework needed. Start the app first for the API and assistant tests.

```bash
# the demo vendor's connector contract (starts its own tiny vendor): paging, clock, tasks, auth, pages
python vendor_mock/tests/smoke.py

# services only (starts its own tiny vendor): sync, train 4, detect, SOP, vendor task round trip, feedback,
# incremental sync + retention, schedules (timer, catch-up, retrain), plan, triage, retrain, ONNX, bundle predict.py
PYTHONPATH=backend python backend/tests/service_smoke.py

# whole flow through the HTTP API against a running server and vendor (prints a timing table)
python backend/tests/api_smoke.py --base http://127.0.0.1:8000 --vendor http://127.0.0.1:8020/mcp/

# assistant: settings, chat with tool calls and hand-overs, proposals, sessions, MCP, SOPs, schedules, live lookups,
# against a built-in fake gateway. It REWRITES the server's assistant settings: run it against a test server
# (SENTINEL_DATA_DIR=data_smoke_assist ...), never your own data/
python backend/tests/assistant_smoke.py
# ...or against a real gateway
python backend/tests/assistant_smoke.py --gateway https://gateway.example --key KEY --model MODEL_ID
```

`service_smoke.py` writes to `data_smoke/` (git-ignored; `SENTINEL_SMOKE_DIR` moves it). The UI type-checks as part of
`npm run build`. Production targets Python 3.11: run the smoke tests in `python:3.11-slim` (with `libgomp1` for
LightGBM) before shipping.

---

## Project layout

```
inventory_anomaly/
├── startup.bat · start.sh          one-click setup + start (Windows / macOS, Linux)
├── run_demo.ps1 · dev.ps1          PowerShell: build-and-serve / dev mode with hot reload
├── requirements.txt                Python dependencies
├── README.md · GUIDE.md            this file · screen-by-screen user guide (both also feed the assistant's doc search)
├── docs/
│   ├── connector-contract.md       the MCP contract a vendor implements (also searchable by the assistant)
│   └── sops/                       standard operating procedures (Markdown + YAML front matter)
├── vendor_mock/                    demo vendor back-office (separate app, :8020)
│   ├── app.py · ui.py              FastAPI app, server-rendered back-office pages
│   ├── connector.py · service.py   the MCP server (connector contract) and its data access, business clock, task inbox
│   ├── db.py · seed.py             SQLite schema, one-off simulation of history + future days
│   ├── sim/synth.py                the retailer simulator with injected, labelled anomalies
│   └── tests/smoke.py              contract checks
├── .claude/launch.json             dev-server definitions (app on :8010, vendor on :8020)
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app, health, static UI, MCP mount
│   │   ├── config.py               paths, limits, planner assumptions, domain constants
│   │   ├── compat.py               pure-Python fallback for blocked SQLAlchemy binaries
│   │   ├── schemas.py              Pydantic request / response models
│   │   ├── mcp_compat.py           mcp 1.x / 2.x bridge (server factory, client session, sync-to-async)
│   │   ├── routers/                connectors, datasets, schedules, sops (+ vendor tasks), training, runs, planner (+ triage), jobs, settings, assistant
│   │   ├── services/
│   │   │   ├── connectors.py       vendor connectors (MCP client calls, masked tokens)
│   │   │   ├── sync.py             incremental pull, local copy, snapshots, retention, data-quality warnings
│   │   │   ├── scheduler.py        schedules, timing, the pipeline job, catch-up, auto-proposed tasks
│   │   │   ├── vendor_tasks.py     approved write-back, outcomes read back as feedback
│   │   │   ├── sops.py             SOP loading, alert → SOP, escalation, filled-in steps
│   │   │   ├── schema_spec.py      the daily column schema
│   │   │   ├── ingest.py           CSV / ZIP import with column mapping; build_dataset (shared with sync)
│   │   │   ├── colstore.py         memory-mapped .npy column store
│   │   │   ├── features.py         the 16 detection signals (ships in model bundles)
│   │   │   ├── detectors.py        z-score, Isolation Forest, LOF, autoencoder, feedback re-ranker
│   │   │   ├── np_engines.py       pure-numpy Isolation Forest and LOF
│   │   │   ├── registry.py         method catalogue, settings, pipeline builders
│   │   │   ├── training.py         sampling, thresholds, evaluation, model selection
│   │   │   ├── calibration.py      P(true) with Beta prior + isotonic PAV
│   │   │   ├── detection.py        scoring, alert grouping, dashboard aggregates
│   │   │   ├── explain.py          reasons in plain sentences, likely-type rules
│   │   │   ├── planner.py          expected value per investigator hour, work lists
│   │   │   ├── triage.py           team decisions, simulated reviews
│   │   │   ├── reranker.py         LightGBM feedback re-ranker
│   │   │   ├── model_export.py     joblib bundle + hand-built ONNX graphs
│   │   │   └── jobs.py, storage.py, datasets.py, exporter.py, envprobe.py
│   │   └── assistant/
│   │       ├── agents.py           Google ADK agent team, prompts, guardrails
│   │       ├── engine.py           LiteLLM model, runner, SSE streaming, sessions
│   │       ├── tools.py            the 32-tool catalogue (shared with MCP)
│   │       ├── adk_tools.py        async adapters that fill ids from the UI selection
│   │       ├── context_pack.py     "current state" injected into every prompt
│   │       ├── proposals.py        confirm-before-run job proposals
│   │       ├── knowledge.py        BM25 search over README, GUIDE, story, connector contract and SOPs
│   │       ├── plain_language.py   labels and glossary
│   │       ├── usage.py            tokens and cost per agent / model
│   │       ├── settings.py         gateway settings, TLS
│   │       └── mcp_server.py       MCP server (tools + resources)
│   └── tests/                      api_smoke, service_smoke, assistant_smoke, fake_gateway
├── frontend/
│   ├── index.html · package.json · package-lock.json · vite.config.ts · tsconfig.json
│   └── src/
│       ├── pages/                  Overview, Executive, Story, Data, Train, Act, Schedules, Models, Experiments, Assistant, Settings
│       ├── components/             ConnectorsCard, SopChecklist, ProposalCard, AlertQueue, AnomalyDashboard, InvestigationPlanner, SeriesDrilldown, TriagePanel, charts, assistant/
│       ├── assistant/              chat context, speech input
│       └── hooks/, api.ts, types.ts, styles.css
├── data/                           runtime only, git-ignored (created on start)
└── data_vendor/                    the demo vendor's SQLite database, git-ignored
```

---

## What is in git and what is not

Everything needed to build and run is tracked: Python and TypeScript source, `requirements.txt`, `package.json`,
**`package-lock.json`** (reproducible UI installs), start scripts, `.claude/launch.json`, docs and the assistant's
knowledge file. `.gitattributes` pins line endings, so `start.sh` keeps LF and `.bat` / `.ps1` keep CRLF.

[`.gitignore`](.gitignore) keeps out everything that is generated or private:

| Ignored | Why |
|---|---|
| `data/`, `data_smoke*/` | snapshots (hundreds of MB), models, runs, triage, exports, connectors (**with their tokens**), schedules, **`settings.json` with the gateway key**, assistant DB; recreated on start |
| `data_vendor*/` | the demo vendor's SQLite database; re-seeded on start |
| `*.joblib`, `*.onnx`, `inventory_sentinel_*.zip` | downloaded model files and bundles |
| `.venv/`, `__pycache__/`, tool caches | rebuilt by the start scripts |
| `frontend/node_modules/`, `frontend/dist/` | rebuilt by `npm install` / `npm run build` |
| `.env*` (except `.env.example`), `*.pem`, `*.key`, `*.log` | secrets and logs |
| editor and OS files, `.claude/settings.local.json` | personal |

A fresh clone plus `startup.bat` / `./start.sh` gives a working app.

---

## Running on locked-down Windows

Windows Smart App Control can block scikit-learn's compiled tree and neighbour modules. Inventory Sentinel detects this
at start-up (`/api/health` lists it) and handles it as follows:

- **Isolation Forest and LOF** run on the built-in numpy engines instead.
- **ONNX export** still works, because the ONNX graphs are built directly with the `onnx` package.
- **Assistant conversations:** if SQLAlchemy's compiled modules are blocked, the app loads SQLAlchemy's own pure-Python
  versions (`backend/app/compat.py`), so conversations are still saved. If that fails too, conversations are kept in
  memory until the app restarts.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "needs Python 3.11 to 3.14" / npm not found | install a supported Python (tick "Add to PATH") and Node.js LTS, re-run the start script |
| Isolation Forest / LOF say "numpy fallback" | Smart App Control blocks scikit-learn's compiled modules; the built-in engine gives the same method |
| "Could not reach … at http://127.0.0.1:8020/mcp/" | the demo vendor is not running: start it (`startup.bat` / `./start.sh` do) or connect your own system |
| Sync says the vendor "is not ready yet" | the demo vendor is still seeding (its dashboard shows progress); try again in a minute |
| "No new trading days since the last sync" | the vendor's day has not closed; on the demo vendor press **Close today's trading (+1 day)**. See SOP `data-feed-failure` |
| A scheduled run failed | Schedules → run history shows the error kind and the SOP; **Test connection** on the connector, then **Run now** |
| Schedules run twice | serve the API with one worker (the scheduler lives in the API process), or set `SENTINEL_SCHEDULER=off` on extra processes |
| Retrain with feedback is greyed out | needs 30 reviewed alerts with at least 5 real and 5 false alarms; simulate a week or review more |
| Import says a column is missing | map it with the JSON column map, e.g. `{"counted_closing": "physical_qty"}` |
| Chat says "configure the gateway" | Settings: URL, key, Connect, model, Test, Save |
| "The certificate of ... is not trusted" | give the CA bundle path or switch verification off for a lab gateway |
| Assistant conversations vanish after restart | SQLAlchemy could not load; `/api/health` says why |
| Anything else | stop the app, delete `data/`, start again |

More detail, demo scripts and every screen: **[GUIDE.md](GUIDE.md)**.
