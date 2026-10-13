import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { errorMessage, useApp, type ActTab } from "../context";
import { AlertQueue } from "../components/AlertQueue";
import { AnomalyDashboard } from "../components/AnomalyDashboard";
import { AlertBellArt, EmptyState } from "../components/Illustrations";
import { InvestigationPlanner } from "../components/InvestigationPlanner";
import { JobProgress } from "../components/JobProgress";
import { Spinner } from "../components/Layout";
import { SeriesDrilldown } from "../components/SeriesDrilldown";
import { TriagePanel } from "../components/TriagePanel";
import { estimateSeconds, fmtDate, fmtDuration, gbp, num } from "../utils";

const TABS: { key: ActTab; label: string }[] = [
  { key: "alerts", label: "Alerts" },
  { key: "dashboard", label: "Dashboard" },
  { key: "planner", label: "Investigation planner" },
  { key: "drill", label: "Drill-down" },
  { key: "triage", label: "Triage & feedback" },
];

export function ActPage() {
  const { runs, selectedRunId, setSelectedRunId, actTab, setActTab, datasets, selectedDatasetId, activeModel, models, watchJob, jobs, toast, config, setPage, cancelJob } = useApp();
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ds = datasets.find((d) => d.id === selectedDatasetId) ?? datasets[0] ?? null;
  const run = runs.find((r) => r.run_id === selectedRunId) ?? runs[0] ?? null;
  const runDs = run ? datasets.find((d) => d.id === run.dataset_id) ?? null : null;
  const job = jobId ? jobs[jobId] ?? null : null;
  const running = !!job && !["done", "failed", "cancelled"].includes(job.status);
  const est = ds && activeModel ? estimateSeconds("detect", { rows: ds.n_rows, scorePer1m: activeModel.metrics.score_seconds_per_1m }, config.timing) : 0;

  const detect = async () => {
    if (!ds || !activeModel) return;
    setBusy(true);
    try {
      const j = await api.runs.detect(ds.id, activeModel.model_id);
      watchJob(j);
      setJobId(j.job_id);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };

  if (!models.length) {
    return (
      <div className="card">
        <EmptyState art={<AlertBellArt />}>
          <b>No detector yet.</b>
          <div className="muted">Train the methods first; the winner becomes the model in use.</div>
          <button className="btn primary mt" onClick={() => setPage(datasets.length ? "train" : "data")}>
            {datasets.length ? "Go to Train" : "Go to Data"} <ArrowRight size={16} aria-hidden="true" />
          </button>
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>3 · Act</h1>
          <p>Score every store-SKU-day, turn odd days into alerts with reasons, plan investigator time and record what teams find.</p>
        </div>
      </div>
      <div className="card">
        <div className="run-bar">
          <label className="field">
            Detection run
            <select value={run?.run_id ?? ""} onChange={(e) => setSelectedRunId(e.target.value)} disabled={!runs.length}>
              {!runs.length ? <option value="">No runs yet</option> : null}
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.model_label}
                  {r.model_in_use ? " (in use)" : ""} · {r.dataset_name.slice(0, 40)} · {fmtDate(r.created_at)} · {num.format(r.incidents)} alerts
                </option>
              ))}
            </select>
          </label>
          <button className="btn primary" disabled={busy || running || !ds || !activeModel} onClick={detect}>
            {busy ? <Spinner /> : null} Run detection{activeModel ? ` with ${activeModel.label}` : ""}
          </button>
          <div className="small muted">
            {run ? `${num.format(run.incidents)} alerts · ${gbp.format(run.value_at_risk_gbp)} at risk · dataset ${run.dataset_name}` : null}
          </div>
          <div className="small muted">{ds ? `${num.format(ds.n_rows)} rows · ${fmtDuration(est)}` : "no dataset"}</div>
        </div>
        {run && !run.model_in_use ? <div className="alert info small mt">This run was produced by {run.model_label}, which is not the model in use now. Run detection again to see the current model's alerts.</div> : null}
        {job ? <JobProgress job={job} onCancel={cancelJob} /> : null}
      </div>
      {!run ? (
        <div className="card">
          <EmptyState art={<AlertBellArt />}>
            <b>No alerts yet.</b>
            <div className="muted">Press “Run detection” to score every day with the model in use.</div>
          </EmptyState>
        </div>
      ) : (
        <>
          <div className="tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t.key} role="tab" aria-selected={actTab === t.key} className={actTab === t.key ? "active" : ""} onClick={() => setActTab(t.key)}>
                {t.label}
              </button>
            ))}
          </div>
          {actTab === "alerts" ? <AlertQueue runId={run.run_id} datasetHasTruth={!!runDs?.has_truth} /> : null}
          {actTab === "dashboard" ? <AnomalyDashboard runId={run.run_id} /> : null}
          {actTab === "planner" ? <InvestigationPlanner runId={run.run_id} /> : null}
          {actTab === "drill" ? <SeriesDrilldown runId={run.run_id} datasetHasTruth={!!runDs?.has_truth} /> : null}
          {actTab === "triage" ? <TriagePanel runId={run.run_id} datasetId={run.dataset_id} modelId={run.model_id} datasetHasTruth={!!runDs?.has_truth} /> : null}
        </>
      )}
    </div>
  );
}
