import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../context";
import { SeverityChip, StatCard, StatusChip, TypeChip } from "../components/Layout";
import { WarehouseArt } from "../components/Illustrations";
import type { Overview } from "../types";
import { fmtDate, gbp, num, plain } from "../utils";

export function OverviewPage() {
  const { setPage, datasets, models, activeModel, runs, jobs, setActTab, setSelectedRunId, openDrill } = useApp();
  const [ov, setOv] = useState<Overview | null>(null);

  // one fetch per real change (the app's lists arrive one by one on start-up), debounced
  const sig = [
    datasets.map((d) => d.id).join(","),
    models.map((m) => m.model_id).join(","),
    activeModel?.model_id ?? "",
    runs.map((r) => r.run_id).join(","),
    Object.values(jobs).filter((j) => j.status === "done").length,
  ].join("|");
  useEffect(() => {
    let live = true;
    const t = window.setTimeout(() => {
      api.overview().then((o) => live && setOv(o)).catch(() => live && setOv(null));
    }, 150);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [sig]);

  const hasData = datasets.length > 0;
  const hasModel = models.length > 0;
  const hasRun = runs.length > 0;
  const base = models.find((m) => m.key === "zscore")?.metrics.average_precision ?? null;
  const best = ov?.best_model;
  const next: { page: "data" | "train" | "act"; label: string } = !hasData
    ? { page: "data", label: "Start by creating a dataset" }
    : !hasModel
      ? { page: "train", label: "Train the detectors" }
      : !hasRun
        ? { page: "act", label: "Run detection and see the alerts" }
        : { page: "act", label: "Work the alerts" };
  const run = ov?.latest_run;

  return (
    <div className="stack">
      <div className="card hero-card">
        <div>
          <h1>Inventory Sentinel</h1>
          <p className="muted" style={{ fontSize: 15, maxWidth: 660 }}>
            Every store, every item, every day: spot stock that is going missing, till behaviour that does not add up, miscounts and
            booking errors, then send warehouse teams to the few places worth a visit. Follow the three business steps in the menu;
            the Analyst area holds every model and run in full detail.
          </p>
          <div className="row mt">
            <button className="btn primary" onClick={() => setPage(next.page)}>
              {next.label} →
            </button>
            <button className="btn" onClick={() => setPage("story")}>
              ▶ Two-minute story for leadership
            </button>
          </div>
        </div>
        <WarehouseArt />
      </div>

      <div className="grid grid-4">
        <StatCard label="Store-SKU-days" value={hasData ? num.format(datasets[0].n_rows) : "–"} sub={hasData ? `${datasets[0].n_stores} stores x ${num.format(datasets[0].n_skus)} SKUs x ${datasets[0].n_days} days` : "no data yet"} />
        <StatCard label="Best detector" value={best ? best.label : "–"} sub={best ? `${plain.ap(best.metrics.average_precision)}${base ? ` · ${plain.lift(best.metrics.average_precision, base)}` : ""}` : "train to compare methods"} />
        <StatCard label="Open alerts" value={run ? num.format(run.kpis.incidents) : "–"} sub={run ? `${run.kpis.by_severity.critical ?? 0} critical · ${run.kpis.stores_affected} stores` : "run detection on the Act page"} />
        <StatCard label="Stock value at risk" value={run ? gbp.format(run.kpis.value_at_risk_gbp) : "–"} sub={run ? `latest run · ${run.model_label}` : "valued at cost"} />
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">
            <h2>Find and act on stock problems</h2>
            <span className="chip neutral">Business</span>
          </div>
          <div className="pipeline">
            {[
              { n: 1, title: "Data", done: hasData, page: "data" as const, desc: hasData ? `${num.format(datasets[0].n_rows)} store-SKU-days ready in “${datasets[0].name}”.` : "Generate 5 million realistic store-SKU-days with hidden problems, or import your own counts." },
              { n: 2, title: "Train", done: hasModel, page: "train" as const, desc: hasModel ? `${num.format(models.length)} models trained${best ? `; best is ${best.label}` : ""}.` : "Four methods compete on history; the exam is the last four weeks." },
              { n: 3, title: "Act", done: hasRun, page: "act" as const, desc: hasRun ? "Alerts, dashboard, investigation planner, drill-down and triage." : "Score every day, get alerts with reasons, plan investigator time." },
            ].map((s) => (
              <div key={s.n} className={`step-card ${s.done ? "done" : ""}`}>
                <div className="n">{s.done ? "✓" : s.n}</div>
                <h3>{s.title}</h3>
                <p className="small muted" style={{ minHeight: 54 }}>
                  {s.desc}
                </p>
                <button className="btn sm" onClick={() => setPage(s.page)}>
                  Open
                </button>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="card-title">
            <h2>Work these first</h2>
            {run ? <span className="small muted">ranked by expected recovery per investigator hour · {run.model_label}</span> : null}
          </div>
          {ov?.top_alerts.length ? (
            <div className="list">
              {ov.top_alerts.map((a) => (
                <div
                  key={a.alert_id}
                  className="list-item"
                  onClick={() => {
                    if (run) setSelectedRunId(run.run_id);
                    openDrill(a.store_id, a.sku_id);
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="title">
                      <span className="mono small">{a.alert_id}</span> {a.store_name} · {a.sku_name}
                    </div>
                    <div className="meta">
                      {a.start_date}
                      {a.n_days > 1 ? ` to ${a.end_date}` : ""} · {gbp.format(a.value_at_risk_gbp)} at risk · {a.reasons[0]}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                    <TypeChip type={a.likely_type} />
                    <SeverityChip severity={a.severity} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No detection run yet. Train the detectors, then run detection on the Act page.</p>
          )}
          {run ? (
            <div className="row mt">
              <button className="btn sm" onClick={() => { setActTab("alerts"); setPage("act"); }}>
                All alerts
              </button>
              <button className="btn sm" onClick={() => { setActTab("planner"); setPage("act"); }}>
                Plan investigator hours
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {ov?.recent_jobs.length ? (
        <div className="card">
          <div className="card-title">
            <h3>Recent jobs</h3>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Status</th>
                  <th className="num">Took</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {ov.recent_jobs.map((j) => (
                  <tr key={j.job_id}>
                    <td>{j.title}</td>
                    <td>
                      <StatusChip status={j.status} />
                    </td>
                    <td className="num">{j.elapsed_seconds ? `${j.elapsed_seconds.toFixed(1)}s` : "–"}</td>
                    <td>{fmtDate(j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
