import { useEffect, useState } from "react";
import { api } from "../api";
import { useAssistant } from "../assistant/AssistantContext";
import { useApp } from "../context";
import { HeatmapGrid } from "../components/AnomalyDashboard";
import { WarehouseArt } from "../components/Illustrations";
import { JobProgress } from "../components/JobProgress";
import { SeverityChip, Spinner, TypeChip } from "../components/Layout";
import { useHeadlineFigures } from "../hooks/useHeadlineFigures";
import { PIPELINE_STEPS, usePipeline } from "../hooks/usePipeline";
import type { Alert } from "../types";
import { compactGbp, gbp, num } from "../utils";

const LABEL: Record<string, string> = { iforest: "Isolation Forest", autoencoder: "Autoencoder", lof: "Local Outlier Factor", ensemble: "Ensemble (Isolation Forest + LOF)" };

/** Executive mode home: the answer on one screen. Three numbers, where it happens, what to do first. */
export function ExecutivePage() {
  const { runs, cancelJob } = useApp();
  const pipe = usePipeline();
  const hasRun = runs.length > 0;

  if (!hasRun || pipe.running || pipe.stage === "failed") {
    return (
      <div className="exec">
        <PipelineCard pipe={pipe} onCancel={cancelJob} hasRun={hasRun} />
        {hasRun && !pipe.running ? <ExecAnswer /> : null}
      </div>
    );
  }
  return (
    <div className="exec">
      <ExecAnswer onRerun={(connectorId) => void pipe.start(connectorId)} />
    </div>
  );
}

function ExecAnswer({ onRerun }: { onRerun?: (connectorId: string) => void }) {
  const { setPage, openDrill, datasets, runs, connectors } = useApp();
  const conn = connectors.find((c) => c.enabled) ?? null;
  const { setDockOpen } = useAssistant();
  const f = useHeadlineFigures();
  const [top, setTop] = useState<Alert[] | null>(null);
  const runId = f.runId;
  useEffect(() => {
    if (!runId) return;
    let stop = false;
    api.overview().then((o) => !stop && setTop(o.top_alerts)).catch(() => !stop && setTop([]));
    return () => {
      stop = true;
    };
  }, [runId]);

  const d = f.dash;
  const base = f.ap.zscore ?? 0;
  const best = Object.entries(f.ap).filter(([k]) => k !== "zscore").sort((a, b) => b[1] - a[1])[0];
  const lift = best && base ? best[1] / base : null;
  const run = runs.find((r) => r.run_id === runId);
  const ds = datasets.find((x) => x.id === run?.dataset_id) ?? datasets[0];

  return (
    <>
      <div className="exec-head">
        <div>
          <h1>Where stock is going missing, and what to do first</h1>
          <p>
            Every store, item and day{ds ? ` (${num.format(ds.n_rows)} checked)` : ""}: the few places that look wrong, why, and what is at stake.
          </p>
        </div>
        <div className="row">
          <button className="btn primary" onClick={() => setPage("story")}>
            ▶ Two-minute story
          </button>
          <button className="btn" onClick={() => setDockOpen(true)}>
            Ask the assistant
          </button>
        </div>
      </div>

      {!d ? (
        <div className="card">
          <Spinner /> Loading the latest results…
        </div>
      ) : (
        <>
          <div className="exec-hero">
            <div className="exec-num">
              <span className="exec-label">Stock value at risk</span>
              <b>{compactGbp(d.run.kpis.value_at_risk_gbp)}</b>
              <span>
                flagged across {num.format(d.run.kpis.stores_affected)} stores, valued at cost
              </span>
            </div>
            <div className="exec-num">
              <span className="exec-label">Worth a visit this week</span>
              <b>{f.plan ? `${num.format(f.plan.n_selected)} alerts` : "–"}</b>
              <span>
                {f.plan ? (
                  <>
                    <b className="ink">{compactGbp(f.plan.expected_recovered)}</b> expected back, <b className="ink">{f.plan.roi.toFixed(0)}x</b> the cost of {num.format(f.plan.hours)} investigator hours
                  </>
                ) : (
                  "planning…"
                )}
              </span>
            </div>
            <div className="exec-num">
              <span className="exec-label">Machine learning vs today's rule</span>
              <b>{lift ? `${lift.toFixed(1)}x better` : "–"}</b>
              <span>
                {best ? `${LABEL[best[0]] ?? best[0]} vs a simple shrinkage threshold at putting real problems first, tested on four held-back weeks` : "train the methods to compare"}
              </span>
            </div>
          </div>

          <div className="exec-grid">
            <div className="card">
              <div className="card-title">
                <h2>Where it happens</h2>
                <button className="btn sm link" onClick={() => setPage("alerts")}>
                  All alerts →
                </button>
              </div>
              <HeatmapGrid d={d} maxRows={8} compact />
            </div>
            <div className="card">
              <div className="card-title">
                <h2>Work these first</h2>
                <button className="btn sm link" onClick={() => setPage("plan")}>
                  Plan the week →
                </button>
              </div>
              {!top ? (
                <Spinner />
              ) : top.length === 0 ? (
                <p className="muted">No open alerts.</p>
              ) : (
                <div className="exec-list">
                  {top.map((a) => (
                    <button key={a.alert_id} className="exec-item" onClick={() => openDrill(a.store_id, a.sku_id, a.alert_id)}>
                      <span className="exec-item-main">
                        <b className="exec-title">
                          {a.store_name} · {a.sku_name}
                        </b>
                        <span className="small muted exec-reason">{a.reasons[0]}</span>
                      </span>
                      <span className="exec-item-side">
                        <TypeChip type={a.likely_type} />
                        <span className="exec-money">{gbp.format(a.value_at_risk_gbp)}</span>
                        <SeverityChip severity={a.severity} />
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="exec-foot small muted">
            <span>
              Model in use: {d.run.model_label}. Figures are estimates on {ds?.kind === "connector" ? `${String(ds.params?.connector_name ?? "vendor")} data through ${ds.date_end}` : ds?.kind === "synthetic" ? "synthetic demo data" : "the loaded data"}.
            </span>
            {onRerun && conn ? (
              <button
                className="btn sm link"
                onClick={() => {
                  if (confirm(`Sync ${conn.name}, retrain and detect again? Usually a minute or two.`)) onRerun(conn.id);
                }}
              >
                Re-run the pipeline
              </button>
            ) : null}
          </div>
        </>
      )}
    </>
  );
}

function PipelineCard({ pipe, onCancel, hasRun }: { pipe: ReturnType<typeof usePipeline>; onCancel: (id: string) => void; hasRun: boolean }) {
  const { connectors, setPage, setMode } = useApp();
  const enabled = connectors.filter((c) => c.enabled);
  const [connectorId, setConnectorId] = useState<string | null>(pipe.connectorId ?? enabled[0]?.id ?? null);
  const chosen = enabled.find((c) => c.id === connectorId) ?? enabled[0] ?? null;
  const order = PIPELINE_STEPS.map((s) => s.key);
  const at = pipe.stage === "failed" ? pipe.failedAt ?? "sync" : pipe.stage;
  const idx = order.indexOf(at as (typeof order)[number]);
  return (
    <div className="card pipeline-card">
      <div className="pipeline-art">
        <WarehouseArt />
      </div>
      <div className="stack" style={{ gap: 14 }}>
        <div>
          <h1 style={{ margin: 0 }}>{pipe.running ? "Finding the anomalies…" : hasRun ? "The last run did not finish" : "See it work in one click"}</h1>
          <p className="muted" style={{ margin: "6px 0 0" }}>
            Reads the latest stock movements from {chosen ? chosen.name : "your inventory system"}, lets four methods compete to learn what normal looks like there, then scores every store, item and day with the winner.
          </p>
        </div>
        <ol className="stepper">
          {PIPELINE_STEPS.map((s, i) => {
            const state = pipe.stage === "idle" ? "todo" : i < idx || pipe.stage === "done" ? "done" : i === idx ? (pipe.stage === "failed" ? "failed" : "active") : "todo";
            return (
              <li key={s.key} className={`step-${state}`}>
                <span className="step-dot" aria-hidden="true">
                  {state === "done" ? "✓" : state === "failed" ? "!" : i + 1}
                </span>
                <span>
                  <b>{s.label}</b>
                  <span className="small muted">{s.help}</span>
                </span>
              </li>
            );
          })}
        </ol>
        {pipe.running && pipe.job ? <JobProgress job={pipe.job} compact onCancel={onCancel} /> : null}
        {pipe.stage === "failed" ? (
          <div className="callout error">
            <b>That step stopped.</b> {pipe.error}
            <div className="row mt">
              <button className="btn primary" onClick={() => void pipe.retry()}>
                Retry
              </button>
              <button className="btn" onClick={pipe.reset}>
                Start over
              </button>
            </div>
          </div>
        ) : null}
        {!pipe.running && pipe.stage !== "failed" ? (
          chosen ? (
            <div className="row" style={{ gap: 10, alignItems: "center" }}>
              {enabled.length > 1
                ? enabled.map((c) => (
                    <button key={c.id} className={`toggle-chip ${chosen.id === c.id ? "on" : ""}`} aria-pressed={chosen.id === c.id} onClick={() => setConnectorId(c.id)}>
                      {c.name}
                    </button>
                  ))
                : null}
              <button className="btn primary lg" onClick={() => void pipe.start(chosen.id)}>
                ▶ Run the whole pipeline
              </button>
            </div>
          ) : (
            <div className="callout">
              <b>Connect a data source first.</b> Sentinel reads your inventory system over MCP (or the bundled demo vendor).
              <div className="row mt">
                <button
                  className="btn primary"
                  onClick={() => {
                    setMode("analyst");
                    setPage("data");
                  }}
                >
                  Go to Data → Connect
                </button>
              </div>
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}
