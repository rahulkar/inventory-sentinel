import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useHeadlineFigures } from "../hooks/useHeadlineFigures";
import { useApp } from "../context";
import { AlertBellArt, CompeteArt, DataInArt, FeedbackArt, HeatmapArt, InvestigationArt, RoadmapArt, SpikeArt, UniversalArt, WarehouseArt } from "../components/Illustrations";
import { MetricBarChart } from "../components/Charts";
import { gbp, num, titleCase, TYPE_LABEL } from "../utils";

interface Slide {
  key: string;
  kicker: string;
  title: string;
  body: ReactNode;
  art: ReactNode;
  wide?: boolean;
}

/** Executive mode: 7 slides, no statistics vocabulary (the alerts slide is folded into "where"). */
const EXEC_KEYS = ["hero", "inputs", "compete", "where", "plan", "feedback", "universal"];

const LABEL: Record<string, string> = { zscore: "Rule of thumb", iforest: "Isolation Forest", autoencoder: "Autoencoder", lof: "Local Outlier Factor" };

const USE_CASES: { title: string; data: string; predicts: string; decision: string }[] = [
  { title: "Customer lifetime value", data: "orders, baskets, recency, loyalty", predicts: "what each customer will spend next year", decision: "put retention budget where it pays back" },
  { title: "Vendor performance", data: "deliveries, defects, invoices, lead times", predicts: "which suppliers are drifting from normal", decision: "re-source early, negotiate on evidence" },
  { title: "Demand forecasting", data: "sales history, calendar, weather", predicts: "units per store per week", decision: "buy and allocate the right quantities" },
  { title: "Returns prediction", data: "orders, product, channel, size", predicts: "the chance an order comes back", decision: "sizing guidance, policy, logistics capacity" },
  { title: "Markdown timing", data: "sell-through, price, stock on hand", predicts: "the best week to mark down", decision: "protect margin instead of blanket discounts" },
  { title: "Store staffing", data: "footfall, trading hours, events", predicts: "hourly demand per store", decision: "rotas that match the queue, not the habit" },
  { title: "Influencer matching", data: "audience profiles, past campaigns", predicts: "creator fit and expected engagement", decision: "spend on creators who move the right customers" },
  { title: "Loyalty app engagement", data: "app events, opens, redemptions", predicts: "who is about to stop using the app", decision: "re-engage before the lapse, not after" },
];

export function StoryPage() {
  const { setPage, mode } = useApp();
  const exec = mode === "exec";
  const f = useHeadlineFigures();
  const [present, setPresent] = useState(false);
  const [index, setIndex] = useState(0);
  const liveTag = f.live ? <span className="chip status-done">live numbers from this session</span> : <span className="chip neutral">illustrative numbers until detection has run</span>;
  const best = Object.entries(f.ap).filter(([k]) => k !== "zscore").sort((a, b) => b[1] - a[1])[0];
  const base = f.ap.zscore ?? 0;

  const allSlides: Slide[] = useMemo(
    () => [
      {
        key: "hero",
        kicker: "Inventory anomaly detection",
        title: "Stock that vanishes, found in days instead of quarters",
        body: (
          <>
            <p>Retailers lose 1.5-2% of sales to shrinkage: theft from outside and inside, till fraud, miscounts, short deliveries and typing mistakes. Audits find it weeks later by looking everywhere.</p>
            <p>Inventory Sentinel looks at every item in every store every day and points warehouse teams at the few places that look wrong today, with the reason and the money at stake.</p>
            <div className="story-stats">
              <div>
                <b>{num.format(f.rows)}</b>
                <span>store-SKU-days checked</span>
              </div>
              <div>
                <b>{num.format(f.critical)}</b>
                <span>critical alerts</span>
              </div>
              <div>
                <b>{gbp.format(f.valueAtRisk)}</b>
                <span>stock value flagged</span>
              </div>
            </div>
            {liveTag}
          </>
        ),
        art: <WarehouseArt />,
      },
      {
        key: "inputs",
        kicker: "What goes in",
        title: "Data the business already records",
        body: (
          <ul className="story-list">
            <li>
              <b>Daily stock counts</b>: what the books expect on the shelf and what was counted
            </li>
            <li>
              <b>Movements</b>: deliveries, sales, returns, transfers and recorded write-offs
            </li>
            <li>
              <b>Till behaviour</b>: keyed-in items, voided lines, overrides, after-hours scans
            </li>
            <li>
              <b>Context</b>: store, region, category, unit cost, promotions, and past loss-prevention flags
            </li>
            <li className="muted">
              The demo: {num.format(f.stores)} stores x {num.format(f.skus)} SKUs x {f.days} days, with {num.format(f.incidentsHidden)} problems hidden inside and an answer key kept aside.
            </li>
          </ul>
        ),
        art: <DataInArt />,
      },
      {
        key: "learn",
        kicker: "How it learns",
        title: "Learn what normal looks like, flag what is not",
        body: (
          <>
            <p>No labels needed. From history, the methods learn how big the daily gap between expected and counted stock usually is for each item, how fast it sells once promotions are allowed for, and how often each store keys items by hand or voids lines.</p>
            <p>A day is unusual when signals move together in a way history rarely shows: stock going missing for a week while the till shows extra voids, or a gap that the next count reverses.</p>
          </>
        ),
        art: <SpikeArt />,
      },
      {
        key: "compete",
        kicker: "Why trust it",
        title: "Four detectives compete; the exam decides",
        body: (
          <>
            <p>
              A rule of thumb (how far today's shrinkage is from normal) is the baseline. The last four weeks are held back as an exam, marked with the hidden answer key. {best ? <><b>{LABEL[best[0]] ?? best[0]}</b> puts real problems first {base ? `${(best[1] / base).toFixed(1)}x` : ""} better than the rule of thumb.</> : null}
            </p>
            {exec && base ? (
              <MetricBarChart rows={Object.entries(f.ap).map(([k, v]) => ({ label: LABEL[k] ?? k, value: v / base, highlight: best?.[0] === k }))} metric="Times as good as the rule of thumb at ranking real problems first" height={170} format={(v) => `${v.toFixed(1)}x`} />
            ) : (
              <MetricBarChart rows={Object.entries(f.ap).map(([k, v]) => ({ label: LABEL[k] ?? k, value: v, highlight: best?.[0] === k }))} metric="Average precision" height={170} format={(v) => v.toFixed(2)} />
            )}
            <p className="small muted">Machine learning wins most on till fraud and internal theft, which never show up as one big shrinkage day.</p>
          </>
        ),
        art: <CompeteArt />,
        wide: true,
      },
      {
        key: "alerts",
        kicker: "What comes out",
        title: "An alert a team can act on",
        body: (
          <>
            <ul className="story-list">
              <li>
                <b>Severity</b>: medium, high or critical
              </li>
              <li>
                <b>Likely type</b>: external or internal theft, till fraud, counting, receiving or data-entry error, sales pattern change
              </li>
              <li>
                <b>Reasons in plain words</b> and the <b>money at risk</b>
              </li>
              <li>
                <b>P(true)</b>: out of alerts like this one, how many turn out to be real
              </li>
            </ul>
            {f.top ? (
              <div className="usecase" style={{ marginTop: 10 }}>
                <b>
                  {f.top.alert_id} · {f.top.store_name} · {f.top.sku_name}
                </b>
                <span>
                  {TYPE_LABEL[f.top.likely_type]} · {gbp.format(f.top.value_at_risk_gbp)} at risk · P(true) {Math.round(f.top.p_true * 100)}%
                </span>
                <span>{f.top.reasons[0]}</span>
              </div>
            ) : null}
          </>
        ),
        art: <AlertBellArt />,
      },
      {
        key: "where",
        kicker: "Where it happens",
        title: exec ? "Patterns, and alerts a team can act on" : "Patterns, not just single alerts",
        body: (
          <>
            <p>The dashboard shows alerts and money at risk by day, a store x category heatmap, and the stores, items and warehouse teams that need attention, so regional managers see patterns early.</p>
            {f.topStores.length ? (
              <ul className="story-list">
                {f.topStores.map((s) => (
                  <li key={s.key}>
                    <b>{s.label}</b>: {gbp.format(s.value_gbp)} at risk across {s.alerts} alerts
                  </li>
                ))}
                {f.topCats.length ? <li className="muted">Top categories: {f.topCats.map((c) => titleCase(c.label)).join(", ")}</li> : null}
              </ul>
            ) : null}
            {exec && f.top ? (
              <div className="usecase" style={{ marginTop: 10 }}>
                <b>
                  Example alert: {f.top.store_name} · {f.top.sku_name}
                </b>
                <span>
                  {TYPE_LABEL[f.top.likely_type]} · {gbp.format(f.top.value_at_risk_gbp)} at risk · {f.top.warehouse_team} team
                </span>
                <span>{f.top.reasons[0]}</span>
              </div>
            ) : null}
          </>
        ),
        art: <HeatmapArt />,
      },
      {
        key: "plan",
        kicker: "From alert to action",
        title: "Plan the investigators' week",
        body: (
          <>
            <p>Investigator time is the scarce resource. The planner ranks alerts by expected recovery per hour and hands each warehouse team its work list.</p>
            {f.plan ? (
              <>
                <MetricBarChart
                  rows={[
                    { label: "Ranked by the model", value: f.plan.expected_recovered, highlight: true },
                    { label: "Same hours, biggest £ first", value: f.plan.naive_expected },
                    { label: "Cost of the hours", value: f.plan.cost },
                  ]}
                  metric="Expected recovery"
                  height={150}
                  format={(v) => gbp.format(v)}
                />
                <p className="small muted">
                  {f.plan.hours.toFixed(0)} hours at {gbp.format(f.plan.hourly_cost)}/hour: {num.format(f.plan.n_selected)} alerts, return {f.plan.roi.toFixed(1)}x on cost. Estimates; they depend on the recovery rate and {exec ? "how often alerts like these turn out real" : "P(true)"}.
                </p>
              </>
            ) : (
              <p className="muted">Run detection to see the plan with live numbers.</p>
            )}
          </>
        ),
        art: <InvestigationArt />,
        wide: true,
      },
      {
        key: "feedback",
        kicker: "It gets better",
        title: "Teams teach the model",
        body: (
          <>
            <p>Every alert a team closes (confirmed theft, counting error, process issue or false alarm) is remembered. {exec ? "The model learns from it and ranks the next alerts better." : "The feedback recalibrates P(true) and trains a re-ranker on top of the detector."}</p>
            {f.fe?.base && f.fe.reranker ? (
              <MetricBarChart
                rows={[
                  { label: "Detector alone", value: Number(f.fe.base.value_captured_pct ?? 0) },
                  { label: "With team feedback", value: Number(f.fe.reranker.value_captured_pct ?? 0), highlight: true },
                ]}
                metric="Share of lost money on flagged days"
                height={120}
                format={(v) => `${v.toFixed(0)}%`}
              />
            ) : null}
            <p className="small muted">Judged only on days nobody reviewed, so the improvement is honest.</p>
          </>
        ),
        art: <FeedbackArt />,
      },
      {
        key: "universal",
        kicker: "One engine, many questions",
        title: "The same four steps answer other questions",
        body: (
          <>
            <p>
              <b>Gather what is recorded → learn what normal looks like → flag and explain → rank actions by value.</b> Change the data, keep the engine, the honest exam and the playbook.
            </p>
            <div className="usecase-grid">
              {USE_CASES.map((u) => (
                <div key={u.title} className="usecase">
                  <b>{u.title}</b>
                  <span>
                    <em>Data:</em> {u.data}
                  </span>
                  <span>
                    <em>Answers:</em> {u.predicts}
                  </span>
                  <span>
                    <em>Decision:</em> {u.decision}
                  </span>
                </div>
              ))}
            </div>
          </>
        ),
        art: <UniversalArt />,
        wide: true,
      },
      {
        key: "live",
        kicker: "Getting to live",
        title: "Laptop today, nightly in production next",
        body: (
          <>
            <ol className="story-list numbered">
              <li>
                <b>Pilot</b>: one region's real counts and till logs; loss prevention reviews the alerts for four weeks.
              </li>
              <li>
                <b>Prove it</b>: compare recovered value and audit hours with the previous quarter.
              </li>
              <li>
                <b>Run it</b>: nightly scoring in the data platform, alerts in the warehouse team's task tool, monthly retraining with their feedback.
              </li>
            </ol>
            <p>Built with open-source tools and no licence cost. The trained models export as a bundle or ONNX for any system.</p>
          </>
        ),
        art: <RoadmapArt />,
      },
    ],
    [f, liveTag, best, base, exec],
  );
  const slides = useMemo(() => (exec ? allSlides.filter((x) => EXEC_KEYS.includes(x.key)) : allSlides), [exec, allSlides]);

  const go = useCallback((d: number) => setIndex((i) => Math.max(0, Math.min(slides.length - 1, i + d))), [slides.length]);
  useEffect(() => {
    if (!present) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") go(1);
      else if (e.key === "ArrowLeft" || e.key === "PageUp") go(-1);
      else if (e.key === "Escape") setPresent(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [present, go]);

  if (present) {
    const s = slides[index];
    return (
      <div className="present" onClick={(e) => { if ((e.target as HTMLElement).classList.contains("present")) go(1); }}>
        <div className={`present-slide ${s.wide ? "wide" : ""}`}>
          <div className="present-art">{s.art}</div>
          <div className="present-text">
            <div className="kicker">{s.kicker}</div>
            <h1>{s.title}</h1>
            <div className="story-body">{s.body}</div>
          </div>
        </div>
        <div className="present-bar">
          <button className="btn sm" onClick={() => go(-1)} disabled={index === 0}>
            ← Previous
          </button>
          <div className="dots">
            {slides.map((x, i) => (
              <button key={x.key} className={i === index ? "on" : ""} onClick={() => setIndex(i)} aria-label={x.title} />
            ))}
          </div>
          <button className="btn sm" onClick={() => go(1)} disabled={index === slides.length - 1}>
            Next →
          </button>
          <button className="btn sm" onClick={() => setPresent(false)}>
            Exit
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="stack story">
      <div className="page-header">
        <div>
          <h1>How it works</h1>
          <p>A two-minute story for the leadership team: what goes in, how the methods learn what normal looks like, what comes out, and why it pays. Press Present for a full-screen walkthrough.</p>
        </div>
        <div className="row">
          <button className="btn primary" onClick={() => { setIndex(0); setPresent(true); }}>
            ▶ Present
          </button>
          <button className="btn" onClick={() => setPage(exec ? "overview" : "data")}>
            Try it
          </button>
        </div>
      </div>
      {slides.map((s, i) => (
        <section key={s.key} className={`story-section ${i % 2 ? "flip" : ""} ${s.wide ? "wide" : ""}`}>
          <div className="story-art">{s.art}</div>
          <div className="story-text">
            <div className="kicker">
              {String(i + 1).padStart(2, "0")} · {s.kicker}
            </div>
            <h2>{s.title}</h2>
            <div className="story-body">{s.body}</div>
          </div>
        </section>
      ))}
      <div className="next-step">
        <div>
          <h3 style={{ margin: "2px 0" }}>See it on real-sized data</h3>
          <div className="muted">{exec ? "One click runs the whole pipeline: the vendor's latest data, four methods competing, then every store, item and day scored." : "Sync a vendor, train four methods on its history, run detection, follow the SOPs and plan a week of investigations."}</div>
        </div>
        <button className="btn primary" onClick={() => setPage(exec ? "overview" : "data")}>
          {exec ? "See the answer →" : "Start with Data →"}
        </button>
      </div>
    </div>
  );
}
