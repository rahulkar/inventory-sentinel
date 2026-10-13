import { ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import { C, MetricBarChart, PRCurveChart } from "../components/Charts";
import { EmptyChartArt, EmptyState } from "../components/Illustrations";
import { StatusChip } from "../components/Layout";
import type { Experiment } from "../types";
import { fmtDate, num } from "../utils";
import { Leaderboard } from "./TrainPage";

const COLORS: Record<string, string> = { zscore: "#5f6878", iforest: C.series, autoencoder: "#7a1fa2", lof: "#0e7490", ensemble: "#b45309", reranker: C.navy };

export function ExperimentsPage() {
  const { models, jobs, toast, setPage, activateModel, datasets } = useApp();
  const [runs, setRuns] = useState<Experiment[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  useEffect(() => {
    api.experiments().then(setRuns).catch((e) => toast(errorMessage(e), "error"));
  }, [models, jobs, toast]);
  const run = runs.find((r) => r.job_id === openId) ?? runs[0] ?? null;
  const ds = run ? datasets.find((d) => d.id === run.dataset_id) : null;
  const base = run?.models.find((m) => m.key === "zscore")?.metrics.average_precision ?? null;
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Experiments</h1>
          <p>Every training run, rebuilt from the saved models so it survives restarts: the leaderboard, precision-recall curves and the dataset each run used.</p>
        </div>
        <button className="btn" onClick={() => setPage("train")}>
          New run <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
      {!runs.length ? (
        <div className="card">
          <EmptyState art={<EmptyChartArt />}>
            <b>No runs yet.</b>
            <div className="muted">Each training run shows up here with its leaderboard.</div>
          </EmptyState>
        </div>
      ) : (
        <div className="grid grid-side">
          <div className="card">
            <div className="card-title">
              <h3>Runs</h3>
            </div>
            <div className="list">
              {runs.map((r) => (
                <div key={r.job_id} className={`list-item ${run?.job_id === r.job_id ? "selected" : ""}`} onClick={() => setOpenId(r.job_id)}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="title">
                      {r.run_name} <StatusChip status={r.status} />
                    </div>
                    <div className="meta">
                      {r.dataset_name} · {r.models.length} model{r.models.length === 1 ? "" : "s"}
                      {r.train_sample_size ? ` · ${num.format(r.train_sample_size)} training days` : ""} · {fmtDate(r.created_at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          {run ? (
            <div className="stack">
              <div className="card">
                <div className="card-title">
                  <h2>{run.run_name}</h2>
                  <span className="small muted">
                    {run.dataset_name} · {run.job_id}
                  </span>
                </div>
                {run.live && run.live.status === "running" ? <div className="alert info small">Running: {run.live.progress.done ?? 0}/{run.live.progress.total ?? 0} methods done.</div> : null}
                <Leaderboard models={run.models} baseAp={base} onUse={activateModel} />
              </div>
              <div className="grid grid-2">
                <div className="card">
                  <h3>Precision vs recall</h3>
                  <PRCurveChart curves={run.models.map((m) => ({ name: m.label, points: m.metrics.pr_curve, color: COLORS[m.key] ?? C.muted }))} height={240} />
                </div>
                <div className="card">
                  <h3>Average precision</h3>
                  <MetricBarChart rows={run.models.map((m) => ({ label: m.label, value: m.metrics.average_precision ?? 0, highlight: m.model_id === run.best_model_id }))} metric="Average precision" format={(v) => v.toFixed(3)} />
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}
      {run && ds ? (
        <div className="card">
          <div className="card-title">
            <h3>Dataset used · {ds.name}</h3>
            <span className="small muted">
              {num.format(ds.n_rows)} rows · exam from {ds.test_from_date}
            </span>
          </div>
          <div className="table-wrap" style={{ maxHeight: 300 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Column</th>
                  <th className="num">Mean</th>
                  <th className="num">Std</th>
                  <th className="num">Median</th>
                  <th className="num">95th pct</th>
                  <th className="num">Max</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ds.stats?.numeric ?? {}).map(([c, s]) => (
                  <tr key={c}>
                    <td>
                      {ds.columns.find((x) => x.name === c)?.label ?? c}
                      <div className="small muted mono">{c}</div>
                    </td>
                    <td className="num">{s.mean.toFixed(2)}</td>
                    <td className="num">{s.std.toFixed(2)}</td>
                    <td className="num">{num.format(s.p50)}</td>
                    <td className="num">{num.format(s.p95)}</td>
                    <td className="num">{num.format(s.max)}</td>
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
