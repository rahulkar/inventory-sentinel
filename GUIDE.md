# Inventory Sentinel: user guide

Inventory Sentinel finds unusual stock movements in a retailer's daily store x SKU records, read from their inventory
system over MCP: stock that goes missing, till behaviour that does not add up, miscounts, deliveries booked in wrong,
typing mistakes and items that stop selling while the system says they are in stock. It turns them into alerts with
reasons, says what to do next from the SOPs, raises approved tasks back in the vendor's system, runs on a schedule, plans
investigator time, and learns from what teams find.

This guide covers **how to use** each screen. For the algorithms, the models used and how the AI works, see the
[README](README.md#algorithms-how-detection-works).

## 1. Start

- **Windows:** double-click `startup.bat`. **macOS / Linux:** `./start.sh`.
- The script checks for **Python 3.11 to 3.14** and Node.js 18+, creates `.venv`, installs packages, builds the UI,
  starts the **demo vendor back-office** on http://127.0.0.1:8020 (a simulated retailer system; it seeds itself in under
  a minute on first start) and opens Sentinel at http://127.0.0.1:8000. The first run takes a few minutes; later runs
  start in seconds.
- Options: `--no-browser`, `--port 8080`, `--dev` (live reload on :5173), `--no-vendor` (connect your own system instead).
- No Docker, no database, and no AI gateway needed to start. The assistant is optional (section 7).

## 2. The screens

The app opens in **Executive mode** (Overview, Alerts, Plan, Story: the answer on one screen, no statistics vocabulary).
The **Executive | Analyst** switch, top right, shows every screen below; the browser remembers the choice.

| Area | Screen | What it is for |
|---|---|---|
| Story | **How it works** | Two-minute leadership story with live numbers; **Present** opens full-screen slides (arrow keys, Esc) |
| Business | **1 Data** | Connect a vendor system over MCP and sync it (or import a CSV); look at the tables; export a ZIP |
| Business | **2 Train** | Four detection methods compete; the winner becomes the model in use |
| Business | **3 Act** | Run detection, then Alerts, Dashboard, Investigation planner, Drill-down (with the SOP), Triage & feedback |
| Operations | **Schedules** | Timed sync → model → detect pipelines; approvals for vendor tasks from scheduled runs |
| Analyst | **Models** | Every model with metrics, signals, thresholds, drivers and export (bundle or ONNX) |
| Analyst | **Experiments** | Every training run with its leaderboard and the dataset it used |
| Assistant | **Assistant** | Full-page chat, conversations, the agent team's usage and cost |
| Settings | **⚙** | The LiteLLM gateway for the assistant |

## 3. Data

### Connect a data source

Sentinel reads a retailer's inventory system through a **connector**: the system's MCP server, implementing the
[connector contract](docs/connector-contract.md). On **1 Data → Connect a data source**:

1. **Add a connector**: a name, the MCP URL (the demo vendor is `http://127.0.0.1:8020/mcp/`, pre-registered by the
   start scripts) and an access token if the system needs one. **Test connection** shows the vendor, its stores and
   products, the dates it holds and whether it offers a demo answer key. Tokens are never shown again after saving.
2. **Sync now** pulls the vendor's daily stock movements into a **snapshot** of the last 120 days (about 30 s for 1.2M rows
   the first time). Later syncs pull only the new days plus the last 3 (late corrections), so they take seconds.
   **Full re-sync** pulls everything again.
3. Each sync shows warnings worth acting on: **no new trading days** (the vendor's day has not closed, so follow SOP
   *data-feed-failure*), missing days, or a short last day.

Each snapshot is a dataset in **Your datasets**. Sentinel keeps the newest three per connector, and never removes the data
the model in use was trained on. Team decisions belong to the connector, so they carry over to every new snapshot.

**Why train on the vendor's own data?** The methods learn what normal looks like *in these stores*: their delivery
days, count noise, till habits and promotions. A model trained elsewhere would flag this estate's normal as unusual.

### The demo vendor back-office (http://127.0.0.1:8020)

A simulated retailer, Demo Retail Co., with its own database and screens: **Dashboard** (business clock, counts, recent
tasks), **Stores**, **Products**, **Stock ledger** (one item in one store, day by day), **Loss prevention** flags,
**Tasks from Sentinel** (the inbox where store staff work the tasks Sentinel raised and record an outcome) and a
**Demo answer key** page for presenters.

- **The business clock** follows the calendar: each night the day's trading closes and becomes visible to Sentinel.
  **Close today's trading (+1 day)** fast-forwards it for demos. That is how schedules get new data to work on.
- **Reset demo data…** throws everything away and simulates a fresh estate.

Its data is a realistic retailer: stores (region, format, warehouse team), SKUs (category, unit cost) and one row per SKU
per store per day with opening stock, deliveries, sales, returns, transfers, recorded adjustments, expected and counted
closing stock, and till behaviour (scans, keyed-in items, voids, overrides, after-hours scans, units scanned at receiving).
The default is 40 stores x 250 SKUs with 150 days of history and 120 more days to reveal.

Seven kinds of problem are injected, each with its own fingerprint:

| Type | What happens |
|---|---|
| External theft | Stock goes missing for several days, more on high-risk items and hotspot stores |
| Internal theft | Several items go missing in one store on the same night, with after-hours scans |
| Till / scan fraud | Sweethearting (voids, overrides, keyed-in items) or refund fraud (returns that never come back) |
| Counting error | A miscount that the next count reverses |
| Receiving error | A delivery booked in at a different quantity from what arrived |
| Data-entry error | A quantity typed ten times too large, or with the wrong sign |
| Sales pattern change | Phantom stock (no sales while the system shows stock) or an unexplained spike |

Ordinary noise is deliberately realistic so a naive rule raises false alarms: promotions, delivery-day noise, new lines,
count noise that grows with stock, and small background shrink.

**Loss-prevention flags** are partial and noisy, like the real thing: by default 40% of thefts and 20% of other problems
were ever flagged (each reported a few days later), 10% carry the wrong type, and a few flag ordinary days. **The demo
answer key** (which rows are injected problems) lives inside the demo vendor. Sentinel reads it only to mark the
methods' homework, never as a model input. A real vendor has none. Tick "show the demo answer key" in previews and
drill-downs to see it.

### Import a CSV

No connector yet? **Manual import** takes a CSV with one row per store, SKU and day. Required: date, store, SKU, counted
closing stock, and either expected closing stock or opening + received + sold. Common column names are recognised (store,
site, sku, article, book_qty, soh_counted, receipts, voids...); map others with the JSON column map. Optional: a ZIP with
stores.csv, skus.csv (category, unit_cost), lp_flags.csv. Missing scan columns switch the matching signals off, with a note.

**Export** builds a ZIP (daily.csv, stores.csv, skus.csv, lp_flags.csv, answer_key.csv if any, metadata.json) that can be
imported again later.

## 4. Train

Five methods learn what a normal day looks like from the history window, with no labels:

| Method | Idea |
|---|---|
| Rule of thumb | How many robust standard deviations today's shrinkage is from normal for the category (the baseline) |
| Isolation Forest | Random splits isolate unusual days quickly |
| Autoencoder | A small neural network rebuilds normal days; what it cannot rebuild is unusual |
| Local Outlier Factor | Days in a sparser neighbourhood than their neighbours |
| Ensemble | Isolation Forest and LOF together: they miss different problems, so adding up how surprising each finds a day ranks real problems higher |

They look at **signals scaled to be quiet on ordinary days**: shrinkage today and over 7 days against the item's own count
noise, gaps that reverse yesterday's, sales against the promotion-adjusted normal, missed sales in a no-sales run,
deliveries booked against scanned, adjustment size, returns, keyed-in items, voids and overrides against the store's habit,
after-hours scans, and store-wide shrink that day.

The last 28% of days are the **exam**. The demo vendor's answer key (or, for a real vendor, loss-prevention flags) marks each method:

- **Average precision** (decides the winner): how well the ranking puts real problems first; 1.0 is perfect.
- **Real in the top 1,000**: of the 1,000 most unusual exam days, how many were real problems.
- **Incidents caught**: share of hidden incidents with at least one flagged day.
- **Value caught**: share of the money lost in hidden incidents that falls on flagged days.

The **alert rate** (0.8% by default) sets how many training days score above the alert threshold; high and critical are the
99.8th and 99.95th percentiles. The best method becomes the **model in use**.

On machines where Windows Smart App Control blocks scikit-learn's compiled tree and neighbour modules, Isolation Forest and
LOF run on a built-in numpy engine (same method, a little slower). The Train page and `/api/health` say which engine is used.

## 5. Act

Press **Run detection** to score every store-SKU-day with the model in use (about 1-2 minutes at 5 million rows).
Flagged days of the same item in the same store are grouped into **alerts** (gaps of one quiet day are bridged).

- **Alerts**: filter by severity, likely type and status; sort by unusualness, money, P(true) or date; open an alert for
  the reasons, the money at risk, P(true), **What to do** (the SOP) and the triage buttons. CSV download of every alert.
- **Dashboard**: alerts and money by day (by severity or likely type), a store x category heatmap, top stores, teams
  and categories, and (demo vendor) how many hidden incidents the run caught.
- **Investigation planner**: set the hours available and the cost of an hour. Alerts are ranked by expected recovery per
  hour; the page shows alerts worked, expected recovery, return on cost, the hours beyond which an hour returns less than
  it costs, what more hours would buy against working down by £ at risk, and work lists per warehouse team (ZIP or CSV).
  Book-keeping errors count only a small share of their value because correcting a record does not recover money. The
  figures are estimates that depend on the recovery rate and P(true).
- **Drill-down**: one item in one store over time: expected against counted stock, the daily gap, flagged days shaded,
  loss-prevention flags and (optionally) the demo answer key, with the reasons for every flagged day, and **What to do**
  for the alert (see below).
- **Triage & feedback**: decisions (confirmed theft, counting error, process issue, false alarm) are remembered per alert and
  carry across runs and snapshots. Closed vendor tasks arrive here by themselves (source "vendor task").
  **Simulate a week of team reviews** (demo vendor) fills in decisions from the answer key with some
  noise. **Recalibrate P(true)** learns from the decisions. **Retrain with feedback** trains a re-ranker on top of the
  detector; it is judged only on days nobody reviewed and shown as a before/after table. Use it, then run detection again.

### What to do: SOPs and vendor tasks

Every alert shows the **standard operating procedure** for its likely type (files in `docs/sops/`):

- the **escalation level**, from severity and value at risk: **L1** store team check (72 h), **L2** store manager and
  loss prevention (24 h), **L3** regional loss prevention (4 h), with who to tell;
- the **steps**, filled in with the item, store and dates, each with an owner, a deadline and the evidence to keep. Tick
  them off as you go; the ticks are remembered in this browser;
- **Raise … task** on steps that need store staff (recount, receiving check, till audit, data correction, CCTV review,
  confidential LP review). The confirm panel sets the priority and an optional note. **Send to vendor** puts it in the
  vendor's task inbox. The step then shows the task and its status;
- **Check live stock in the vendor system** reads the item's position right now (not from the snapshot).

When store staff close a task with an outcome, the next sync records it as the team's decision:

| Outcome | Decision |
|---|---|
| confirmed loss | confirmed theft (theft-type alerts) or process issue |
| count corrected | counting error |
| process fixed | process issue |
| no issue | false alarm |

The SOPs never name people. An internal-loss pattern goes to loss prevention only, through a confidential task.

## 6. Schedules

**Schedules** runs the whole pipeline at set times, so alerts are waiting when teams start work.

1. **New schedule**: a name, the connector, **when** (every day, some weekdays, or every few hours, at a time, in a time
   zone) and **which model**:
   - **The model in use**: whatever is active on the Models page when the run starts;
   - **A specific saved model**: the same model every time, so scores stay comparable;
   - **Retrain each run**: pick the algorithms (and their settings under *Algorithm settings*). Each run trains them on
     the fresh snapshot and scores with the best. Optionally retrain at most every N days, and choose whether the new
     model becomes the one in use.
2. Optionally **Propose vendor tasks for new alerts**: severities, minimum £, a maximum per run.
3. *More options*: score the latest snapshot without syncing, and what to do about a run missed while Sentinel was off
   (catch up once, or skip).

The editor shows the plan in a sentence and the next three run times. **Run now** tries it immediately. The **run
history** shows each run's data date, model, new and critical alerts and money at risk. **Alerts →** opens that run on
the Act page. Failed runs show the error and the SOP to follow (*data-feed-failure*).

Tasks proposed by a scheduled run appear under **Waiting for your approval**. Nothing reaches the vendor until someone
presses **Approve and raise**. Proposals expire after 72 hours.

Keep Sentinel running (one process) for schedules to fire; a run that was due while it was off becomes a catch-up run.

## 7. Taking a model elsewhere

On **Models**, "Use this model elsewhere":

- **Model bundle (.zip)**: model.joblib, model.json, features.py, detectors.py, np_engines.py, predict.py and pinned
  requirements. `python predict.py daily.csv scored.csv --skus skus.csv` adds anomaly_score, percentile, severity, is_alert.
- **ONNX**: one float32 input `features` and one output `anomaly_score`, built directly with the onnx package and checked to
  rank 2,000 sample days exactly like the Python model. Runs in any language with onnxruntime. The feedback re-ranker chains
  two models and is bundle-only.

## 8. The assistant

Connect a LiteLLM gateway under **Settings** (URL, key, Connect, pick a model that supports tool calling, Test, Save).
Certificate verification is off by default for lab gateways; switch it on (with a CA bundle path) for production, or set
`LITELLM_SSL_VERIFY=true` / `LITELLM_CA_BUNDLE`.

A front-door agent answers quick questions and hands over to specialists:

| Agent | Handles |
|---|---|
| Data analyst | snapshots and imports, columns, loss-prevention flags, live stock in the vendor system; proposes syncs |
| Model analyst | methods, metrics, drivers, training, feedback retraining, ONNX, model in use |
| Alert investigator | runs, alerts, why something was flagged, the SOP to follow, drill-downs, trends and hotspots; proposes detection and vendor tasks |
| Loss-prevention planner | investigator hours, expected recovery, return on cost, work lists, escalation |
| Operations coordinator | connectors and syncs, schedules (create, change, run, history), vendor tasks, SOPs, failed feeds |
| Explainer | how the app works, glossary, screens, troubleshooting |

The chat sees the page, tab, alert and item you have open, so "why was this flagged?" works on the open alert. Every answer
shows a thinking trail (hand-overs, tools, timings) and its token cost; the microphone uses the browser's speech-to-text.
Anything that creates or changes something becomes a **proposal card** you confirm. Triage decisions are made in the app.
The assistant describes patterns as "consistent with" theft or error and never accuses people. The same 32 tools are an
MCP server at `/mcp/` (resources `sentinel://guide`, `readme`, `glossary`, `story`, `sops`, `sop/<id>`).

**Good questions to ask, by role:**

| You are | Try |
|---|---|
| Executive | "What is the business case?" · "Where are we losing most?" · "What do 200 hours buy us?" |
| Loss-prevention lead | "Plan 120 investigator hours at £28 an hour" · "Compare 60, 120 and 240 hours" · "Which team has the most to do?" |
| Store / area manager | "Show the critical alerts for S012" · "Why was this flagged?" (with an alert open) · "What's the SOP for this alert?" · "What's the stock of K00012 at S003 right now?" |
| Operations | "Set up a daily 6am scan that retrains Isolation Forest and proposes recounts for critical alerts" · "How did last night's run go?" · "Is the vendor feed up to date?" |
| Analyst | "Did machine learning beat the rule of thumb?" · "What does the winner catch by type?" · "What drives Isolation Forest?" |
| New user | "How do I connect our stock system?" · "What does P(true) mean?" · "What should I do next?" |

**What the AI does and does not do.** It reads results through tools and explains them. Every number is computed by
the app, not by the language model. It proposes jobs and changes (sync, train, detect, retrain, export, switch model,
create / change / run a schedule, raise vendor tasks) as cards that you confirm. It never records triage decisions, edits
connectors or tokens, deletes anything or accuses anyone.

**What is sent to the gateway:** your messages, a short summary of what is on screen, and tool results (aggregates
and at most 20 rows per call). Raw datasets and models stay on your machine. Without a gateway nothing leaves it.

**Using the tools from another AI agent (MCP).** While the app is running, any MCP client can connect to
`http://127.0.0.1:8000/mcp/` (streamable HTTP). For example, in Claude Code:

```bash
claude mcp add --transport http inventory-sentinel http://127.0.0.1:8000/mcp/
```

Jobs proposed over MCP still appear as cards in the app's chat for you to confirm.

## 9. Demo scripts

**Three-minute CIO/CTO demo (Executive mode, the default):**

1. **Overview**: read the three numbers left to right: money at risk, alerts worth a visit and what they return, machine
   learning against today's rule. (On an empty install press **Run the whole pipeline** first: it syncs the demo vendor,
   trains and detects in a minute or two.)
2. Point at the darkest cells of **Where it happens**, then click the first item in **Work these first**: the drawer shows
   why it was flagged and the stock story.
3. **Plan**: drag the hours slider and watch alerts worked, expected recovery and return change.
4. **Story → Present** for the seven-slide close; end on "one engine, many questions".
5. Optional: open the chat and ask "What is the business case?".

**Five-minute analyst demo** (switch to **Analyst**, top right):

1. **How it works → Present** (two minutes): the problem, the data, four detectives, alerts, planning, feedback.
2. **Data**: show the connected demo vendor, press **Sync now** (30 s); open the vendor's back-office in another tab to show
   it is a separate system. Show the shrinkage histogram and tick "show the demo answer key" on the daily table.
3. **Train**: train all four (about 2 minutes); read the winner card: Isolation Forest against the rule of thumb.
4. **Act → Run detection**; open the top critical alert, read the reasons and **What to do** (escalation level, steps),
   press **Raise … task → Send to vendor**, then show it in the vendor's **Tasks from Sentinel**; close it with an outcome.
5. **Dashboard**: the heatmap's hot store x category; **Planner**: 120 hours, the return and the team work lists.
6. **Triage**: simulate a week, retrain with feedback, show the before/after table on unreviewed days.
7. **Schedules**: create a daily 06:00 run that retrains Isolation Forest and proposes tasks for critical alerts; **Run now**;
   show the history and the approvals card (the closed task came back as a team decision).
8. Ask the assistant: "Why was the top alert flagged?", "What's the SOP?" and "Plan 120 investigator hours at £28 an hour".

## 10. Working with real data, week after week

1. **Connect** your inventory system (Data → Connect a data source): an MCP adapter in front of it implementing the
   [connector contract](docs/connector-contract.md). Or **import** a few months of daily records as a CSV.
2. **Sync**, then **train** all four methods on that history. Without an answer key, methods are marked against your
   loss-prevention flags. This is a lower bound, because most incidents were never flagged, so compare methods rather than
   reading the numbers as absolute.
3. **Schedule** it: nightly after the day closes, with the model in use (or retraining weekly), proposing tasks for
   critical alerts.
4. Each morning: approve the proposed tasks, work alerts with their **SOP**, and send each warehouse team its work list
   from the **Investigation planner** (ZIP, one CSV per team).
5. Outcomes come back by themselves from closed vendor tasks; record the rest on the Triage tab.
6. After about 30 decisions with at least 5 real problems and 5 false alarms, **Recalibrate P(true)** and
   **Retrain with feedback**. Keep the re-ranker only if its before/after table on unreviewed days is better.

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| "needs Python 3.11 to 3.14" / npm not found | Install a supported Python (tick "Add to PATH") and Node.js LTS, then re-run the start script |
| Isolation Forest / LOF say "numpy fallback" | Windows Smart App Control blocks scikit-learn's compiled modules; the built-in engine is used. Turning Smart App Control off restores scikit-learn's engine (it cannot be turned back on without reinstalling Windows) |
| Assistant conversations vanish after a restart | SQLAlchemy could not load at all, so conversations are kept in memory; `/api/health` says why |
| "Could not reach … :8020/mcp/" | The demo vendor is not running; the start scripts start it (or run `python -m uvicorn vendor_mock.app:app --port 8020`) |
| Sync: the vendor "is not ready yet" | The demo vendor is still seeding; its dashboard shows progress |
| "No new trading days since the last sync" | The vendor's day has not closed. On the demo vendor press **Close today's trading (+1 day)**; for a real system follow SOP *data-feed-failure* |
| A scheduled run failed | Schedules → run history shows the error and the SOP; **Test connection** on the connector, then **Run now** |
| "Raise … task" is missing | The run is on an imported CSV (no vendor to send to), or the vendor does not accept that task type |
| Retrain with feedback is greyed out | It needs 30 reviewed alerts with at least 5 real and 5 false alarms; simulate a week or review more |
| Import says a column is missing | Map it with the JSON column map, e.g. `{"counted_closing": "physical_qty"}` |
| The chat says "configure the gateway" | Settings: URL, key, Connect, model, Test, Save |
| "The certificate of ... is not trusted" | Verification is on; give the CA bundle path or switch verification off for a lab gateway |
| Start clean | Stop the app and delete the `data` folder (and `data_vendor` to re-seed the demo vendor) |
