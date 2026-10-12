# Inventory Sentinel: user guide

Inventory Sentinel finds unusual stock movements in daily store x SKU records: stock that goes missing, till behaviour
that does not add up, miscounts, deliveries booked in wrong, typing mistakes and items that stop selling while the system
says they are in stock. It turns them into alerts with reasons, plans investigator time, and learns from what teams find.

This guide covers **how to use** each screen. For the algorithms, the models used and how the AI works, see the
[README](README.md#algorithms-how-detection-works).

## 1. Start

- **Windows:** double-click `startup.bat`. **macOS / Linux:** `./start.sh`.
- The script checks for **Python 3.11 to 3.14** and Node.js 18+, creates `.venv`, installs packages, builds the UI and
  opens http://127.0.0.1:8000. The first run takes a few minutes; later runs start in seconds.
- Options: `--no-browser`, `--port 8080`, `--dev` (live reload on :5173).
- No Docker, no database, and no AI gateway needed to start. The assistant is optional (section 7).

## 2. The screens

The app opens in **Executive mode** (Overview, Alerts, Plan, Story: the answer on one screen, no statistics vocabulary).
The **Executive | Analyst** switch, top right, shows every screen below; the browser remembers the choice.

| Area | Screen | What it is for |
|---|---|---|
| Story | **How it works** | Two-minute leadership story with live numbers; **Present** opens full-screen slides (arrow keys, Esc) |
| Business | **1 Data** | Generate or import daily records; look at the tables; export a ZIP |
| Business | **2 Train** | Four detection methods compete; the winner becomes the model in use |
| Business | **3 Act** | Run detection, then Alerts, Dashboard, Investigation planner, Drill-down, Triage & feedback |
| Analyst | **Models** | Every model with metrics, signals, thresholds, drivers and export (bundle or ONNX) |
| Analyst | **Experiments** | Every training run with its leaderboard and the dataset it used |
| Assistant | **Assistant** | Full-page chat, conversations, the agent team's usage and cost |
| Settings | **⚙** | The LiteLLM gateway for the assistant |

## 3. Data

**Generate** builds a realistic retailer: stores (region, format, warehouse team), SKUs (category, unit cost) and one row
per SKU per store per day with opening stock, deliveries, sales, returns, transfers, recorded adjustments, expected and
counted closing stock, and till behaviour (scans, keyed-in items, voids, overrides, after-hours scans, units scanned at
receiving). The default is **80 stores x 500 SKUs x 125 days = 5 million rows**, generated in about 30 seconds.

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
were ever flagged, 10% carry the wrong type, and a few flag ordinary days. **The answer key** (which rows are injected
problems) is stored separately, never used as a model input, and only used to mark the methods' homework. Tick
"show the answer key" in previews and drill-downs to see it.

**Import** a CSV with one row per store, SKU and day. Required: date, store, SKU, counted closing stock, and either
expected closing stock or opening + received + sold. Common column names are recognised (store, site, sku, article,
book_qty, soh_counted, receipts, voids...); map others with the JSON column map. Optional: a ZIP with stores.csv, skus.csv
(category, unit_cost), lp_flags.csv. Missing scan columns switch the matching signals off, with a note.

**Export** builds a ZIP (daily.csv, stores.csv, skus.csv, lp_flags.csv, answer_key.csv, metadata.json) that can be imported
again later.

## 4. Train

Four methods learn what a normal day looks like from the history window, with no labels:

| Method | Idea |
|---|---|
| Rule of thumb | How many robust standard deviations today's shrinkage is from normal for the category (the baseline) |
| Isolation Forest | Random splits isolate unusual days quickly |
| Autoencoder | A small neural network rebuilds normal days; what it cannot rebuild is unusual |
| Local Outlier Factor | Days in a sparser neighbourhood than their neighbours |

They look at **signals scaled to be quiet on ordinary days**: shrinkage today and over 7 days against the item's own count
noise, gaps that reverse yesterday's, sales against the promotion-adjusted normal, missed sales in a no-sales run,
deliveries booked against scanned, adjustment size, returns, keyed-in items, voids and overrides against the store's habit,
after-hours scans, and store-wide shrink that day.

The last 28% of days are the **exam**. The answer key marks each method:

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
  the reasons, the money at risk, P(true) and the triage buttons. CSV download of every alert.
- **Dashboard**: alerts and money by day (by severity or likely type), a store x category heatmap, top stores, teams
  and categories, and (synthetic data) how many hidden incidents the run caught.
- **Investigation planner**: set the hours available and the cost of an hour. Alerts are ranked by expected recovery per
  hour; the page shows alerts worked, expected recovery, return on cost, the hours beyond which an hour returns less than
  it costs, what more hours would buy against working down by £ at risk, and work lists per warehouse team (ZIP or CSV).
  Book-keeping errors count only a small share of their value because correcting a record does not recover money. The
  figures are estimates that depend on the recovery rate and P(true).
- **Drill-down**: one item in one store over time: expected against counted stock, the daily gap, flagged days shaded,
  loss-prevention flags and (optionally) the answer key, with the reasons for every flagged day.
- **Triage & feedback**: decisions (confirmed theft, counting error, process issue, false alarm) are remembered per alert and
  carry across runs. **Simulate a week of team reviews** (synthetic data) fills in decisions from the answer key with some
  noise. **Recalibrate P(true)** learns from the decisions. **Retrain with feedback** trains a re-ranker on top of the
  detector; it is judged only on days nobody reviewed and shown as a before/after table. Use it, then run detection again.

## 6. Taking a model elsewhere

On **Models**, "Use this model elsewhere":

- **Model bundle (.zip)**: model.joblib, model.json, features.py, detectors.py, np_engines.py, predict.py and pinned
  requirements. `python predict.py daily.csv scored.csv --skus skus.csv` adds anomaly_score, percentile, severity, is_alert.
- **ONNX**: one float32 input `features` and one output `anomaly_score`, built directly with the onnx package and checked to
  rank 2,000 sample days exactly like the Python model. Runs in any language with onnxruntime. The feedback re-ranker chains
  two models and is bundle-only.

## 7. The assistant

Connect a LiteLLM gateway under **Settings** (URL, key, Connect, pick a model that supports tool calling, Test, Save).
Certificate verification is off by default for lab gateways; switch it on (with a CA bundle path) for production, or set
`LITELLM_SSL_VERIFY=true` / `LITELLM_CA_BUNDLE`.

A front-door agent answers quick questions and hands over to specialists:

| Agent | Handles |
|---|---|
| Data analyst | datasets, columns, the generator, loss-prevention flags; proposes generate / import jobs |
| Model analyst | methods, metrics, drivers, training, feedback retraining, ONNX, model in use |
| Alert investigator | runs, alerts, why something was flagged, drill-downs, trends and hotspots; proposes detection |
| Loss-prevention planner | investigator hours, expected recovery, return on cost, work lists |
| Explainer | how the app works, glossary, screens, troubleshooting |

The chat sees the page, tab, alert and item you have open, so "why was this flagged?" works on the open alert. Every answer
shows a thinking trail (hand-overs, tools, timings) and its token cost; the microphone uses the browser's speech-to-text.
Anything that creates or changes something becomes a **proposal card** you confirm. Triage decisions are made in the app.
The assistant describes patterns as "consistent with" theft or error and never accuses people. The same 24 tools are an
MCP server at `/mcp/` (resources `sentinel://guide`, `readme`, `glossary`, `story`).

**Good questions to ask, by role:**

| You are | Try |
|---|---|
| Executive | "What is the business case?" · "Where are we losing most?" · "What do 200 hours buy us?" |
| Loss-prevention lead | "Plan 120 investigator hours at £28 an hour" · "Compare 60, 120 and 240 hours" · "Which team has the most to do?" |
| Store / area manager | "Show the critical alerts for S012" · "Why was this flagged?" (with an alert open) · "Show the stock story for this item" |
| Analyst | "Did machine learning beat the rule of thumb?" · "What does the winner catch by type?" · "What drives Isolation Forest?" |
| New user | "How do I import my own data?" · "What does P(true) mean?" · "What should I do next?" |

**What the AI does and does not do.** It reads results through tools and explains them. Every number is computed by
the app, not by the language model. It proposes jobs (generate, train, detect, retrain, export, switch model) as cards
that you confirm. It never records triage decisions, deletes anything or accuses anyone.

**What is sent to the gateway:** your messages, a short summary of what is on screen, and tool results (aggregates
and at most 20 rows per call). Raw datasets and models stay on your machine. Without a gateway nothing leaves it.

**Using the tools from another AI agent (MCP).** While the app is running, any MCP client can connect to
`http://127.0.0.1:8000/mcp/` (streamable HTTP). For example, in Claude Code:

```bash
claude mcp add --transport http inventory-sentinel http://127.0.0.1:8000/mcp/
```

Jobs proposed over MCP still appear as cards in the app's chat for you to confirm.

## 8. Demo scripts

**Three-minute CIO/CTO demo (Executive mode, the default):**

1. **Overview**: read the three numbers left to right: money at risk, alerts worth a visit and what they return, machine
   learning against today's rule. (On an empty install press **Run the whole pipeline** first: about a minute.)
2. Point at the darkest cells of **Where it happens**, then click the first item in **Work these first**: the drawer shows
   why it was flagged and the stock story.
3. **Plan**: drag the hours slider and watch alerts worked, expected recovery and return change.
4. **Story → Present** for the seven-slide close; end on "one engine, many questions".
5. Optional: open the chat and ask "What is the business case?".

**Five-minute analyst demo** (switch to **Analyst**, top right):

1. **How it works → Present** (two minutes): the problem, the data, four detectives, alerts, planning, feedback.
2. **Data**: generate 5 million rows (30 s); show the shrinkage histogram and tick "show the answer key" on the daily table.
3. **Train**: train all four (about 2 minutes); read the winner card: Isolation Forest against the rule of thumb.
4. **Act → Run detection**; open the top critical alert, read the reasons, click **See the stock story**.
5. **Dashboard**: the heatmap's hot store x category; **Planner**: 120 hours, the return and the team work lists.
6. **Triage**: simulate a week, retrain with feedback, show the before/after table on unreviewed days.
7. Ask the assistant: "Why was the top alert flagged?" and "Plan 120 investigator hours at £28 an hour".

## 9. Working with real data, week after week

1. **Import** a few months of daily records (Data → Import). Map unrecognised columns with the JSON column map. Add
   `stores.csv` (with `warehouse_team`), `skus.csv` (with `category`, `unit_cost`) and past `lp_flags.csv` if you have them.
2. **Train** all four methods. Without an answer key, methods are marked against your loss-prevention flags. This is a
   lower bound, because most incidents were never flagged, so compare methods rather than reading the numbers as absolute.
3. **Run detection** and send each warehouse team its work list from the **Investigation planner** (ZIP, one CSV per team).
4. **Record outcomes** on the Triage tab as teams report back (confirmed theft, counting error, process issue, false alarm).
5. After about 30 decisions with at least 5 real problems and 5 false alarms, **Recalibrate P(true)** and
   **Retrain with feedback**. Keep the re-ranker only if its before/after table on unreviewed days is better.
6. Next week: import the new days, **Run detection** again. Decisions carry across runs, so reviewed alerts stay reviewed.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| "needs Python 3.11 to 3.14" / npm not found | Install a supported Python (tick "Add to PATH") and Node.js LTS, then re-run the start script |
| Isolation Forest / LOF say "numpy fallback" | Windows Smart App Control blocks scikit-learn's compiled modules; the built-in engine is used. Turning Smart App Control off restores scikit-learn's engine (it cannot be turned back on without reinstalling Windows) |
| Assistant conversations vanish after a restart | SQLAlchemy could not load at all, so conversations are kept in memory; `/api/health` says why |
| Generate refuses the size | Rows = stores x SKUs x days must be between the limits shown; `SENTINEL_MIN_ROWS=50000` lowers the minimum for quick tests |
| Retrain with feedback is greyed out | It needs 30 reviewed alerts with at least 5 real and 5 false alarms; simulate a week or review more |
| Import says a column is missing | Map it with the JSON column map, e.g. `{"counted_closing": "physical_qty"}` |
| The chat says "configure the gateway" | Settings: URL, key, Connect, model, Test, Save |
| "The certificate of ... is not trusted" | Verification is on; give the CA bundle path or switch verification off for a lab gateway |
| Start clean | Stop the app and delete the `data` folder |
