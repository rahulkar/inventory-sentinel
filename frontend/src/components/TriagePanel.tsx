import { useEffect, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { ModelMeta, TriageSummary } from "../types";
import { MetricBarChart, PrecisionLineChart } from "./Charts";
import { EmptyState, FeedbackArt } from "./Illustrations";
import { JobProgress } from "./JobProgress";
import { Help, Spinner, StatCard } from "./Layout";
import { TechnicalDetails } from "./TechnicalDetails";
import { num, OUTCOME_LABEL, plain, TYPE_LABEL } from "../utils";

const METRIC_LABEL: Record<string, string> = {
  average_precision: "Average precision",
  precision_at_k: "Real in the top 1,000",
  incident_recall: "Incidents caught",
  value_captured_pct: "Value caught",
  recall_at_threshold: "Problem days flagged",
};

function fmtMetric(k: string, v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  if (k === "value_captured_pct") return `${v.toFixed(0)}%`;
  if (k === "average_precision") return v.toFixed(3);
  return `${Math.round(v * 100)}%`;
}

export function TriagePanel({ runId, datasetId, modelId, datasetHasTruth }: { runId: string; datasetId: string; modelId: string; datasetHasTruth: boolean }) {
  const { toast, watchJob, jobs, models, activateModel, refreshRuns, setPage } = useApp();
  const [s, setS] = useState<TriageSummary | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [newest, setNewest] = useState<ModelMeta | null>(null);
  const job = jobId ? jobs[jobId] ?? null : null;
  useEffect(() => {
    api.triage.summary(datasetId, runId).then(setS).catch((e) => toast(errorMessage(e), "error"));
  }, [datasetId, runId, tick, toast]);
  const reranker = models.find((m) => m.key === "reranker" && m.dataset_id === datasetId) ?? null;
  useEffect(() => {
    if (!reranker) {
      setNewest(null);
      return;
    }
    api.models.get(reranker.model_id).then(setNewest).catch(() => setNewest(null));
  }, [reranker?.model_id, job?.status]);
  const simulate = async () => {
    setBusy("sim");
    try {
      const r = await api.triage.simulate(runId, 5, 25);
      toast(`Simulated ${r.reviewed} reviews: ${Math.round(r.precision * 100)}% were real problems`, "success");
      setTick((t) => t + 1);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };
  const recalibrate = async () => {
    setBusy("cal");
    try {
      const r = await api.runs.recalibrate(runId);
      toast(`P(true) recalibrated from ${r.reviewed} reviews`, "success");
      await refreshRuns();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };
  const retrain = async () => {
    setBusy("re");
    try {
      const base = models.find((m) => m.model_id === modelId);
      const target = base?.key === "reranker" && base.parent_model_id ? base.parent_model_id : modelId;
      const j = await api.models.retrain(target);
      watchJob(j);
      setJobId(j.job_id);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };
  const reset = async () => {
    if (!confirm("Forget every triage decision on this dataset?")) return;
    try {
      await api.triage.reset(datasetId);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
    setTick((t) => t + 1);
  };
  if (!s) return <Spinner />;
  const fe = newest?.feedback_eval;
  return (
    <div className="stack">
      <div className="grid grid-4">
        <StatCard label="Alerts reviewed" value={num.format(s.reviewed)} sub={s.simulated ? `${num.format(s.simulated)} simulated` : "by your teams"} />
        <StatCard label="Real problems" value={s.precision !== null ? plain.pct(s.precision) : "–"} sub={`${num.format(s.true_alerts)} real · ${num.format(s.false_alarms)} false alarms`} />
        <StatCard label="Still open" value={num.format(s.open_alerts)} sub="in this run" />
        <StatCard label="Retrain with feedback" value={s.can_retrain ? "ready" : "not yet"} sub={s.can_retrain ? "enough decisions to learn from" : `${s.reviewed}/30 reviewed`} />
      </div>
      {s.reviewed === 0 ? (
        <div className="card">
          <EmptyState art={<FeedbackArt />}>
            <b>No decisions recorded yet.</b>
            <div className="muted">Open an alert and mark it confirmed theft, counting error, process issue or false alarm. Each decision makes the next week's alerts better.</div>
            {datasetHasTruth ? (
              <button className="btn primary mt" disabled={busy !== null} onClick={simulate}>
                {busy === "sim" ? <Spinner /> : null} Simulate a week of team reviews
              </button>
            ) : null}
          </EmptyState>
        </div>
      ) : (
        <div className="grid grid-2">
          <div className="card">
            <div className="card-title">
              <h3>
                How many alerts were real, day by day <Help text="Bars: alerts reviewed that day. Line: the share that were real problems." />
              </h3>
            </div>
            <PrecisionLineChart rows={s.by_day} />
          </div>
          <div className="card">
            <div className="card-title">
              <h3>Real problems by likely type</h3>
            </div>
            <MetricBarChart rows={s.by_type.map((g) => ({ label: `${TYPE_LABEL[g.key] ?? g.key} (${g.reviewed})`, value: g.precision }))} metric="Share real" format={(v) => `${Math.round(v * 100)}%`} />
          </div>
        </div>
      )}
      <div className="card">
        <div className="card-title">
          <h2>Teach the model</h2>
        </div>
        <p className="small muted">
          Decisions are remembered per alert and carry across runs. Recalibrating updates P(true) for every open alert from what your teams found. Retraining trains a re-ranker on top of the detector with your decisions and the loss-prevention history; it is judged only on days nobody reviewed, so the improvement is honest.
        </p>
        <div className="row">
          {datasetHasTruth ? (
            <button className="btn" disabled={busy !== null} onClick={simulate}>
              {busy === "sim" ? <Spinner /> : null} Simulate another week of reviews
            </button>
          ) : null}
          <button className="btn" disabled={busy !== null || s.reviewed < 10} onClick={recalibrate}>
            {busy === "cal" ? <Spinner /> : null} Recalibrate P(true)
          </button>
          <button className="btn primary" disabled={busy !== null || !s.can_retrain || (!!job && !["done", "failed", "cancelled"].includes(job.status))} onClick={retrain} title={s.retrain_reason ?? ""}>
            {busy === "re" ? <Spinner /> : null} Retrain with feedback
          </button>
          <span className="spacer" />
          {s.reviewed ? (
            <button className="btn sm danger" onClick={reset}>
              Forget decisions
            </button>
          ) : null}
        </div>
        {!s.can_retrain && s.retrain_reason ? <div className="small muted mt">{s.retrain_reason}</div> : null}
        {job ? <JobProgress job={job} /> : null}
      </div>
      {fe && fe.base && fe.reranker ? (
        <div className="card">
          <div className="card-title">
            <h2>Before and after, on days your team never reviewed</h2>
            {newest && !newest.is_active ? (
              <button className="btn sm primary" onClick={() => activateModel(newest.model_id)}>
                Use the re-ranker
              </button>
            ) : newest ? (
              <span className="chip status-done">re-ranker in use</span>
            ) : null}
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Measure</th>
                  <th className="num">Detector alone</th>
                  <th className="num">With your feedback</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(METRIC_LABEL).map((k) => (
                  <tr key={k}>
                    <td>{METRIC_LABEL[k]}</td>
                    <td className="num">{fmtMetric(k, fe.base?.[k])}</td>
                    <td className="num">
                      <b>{fmtMetric(k, fe.reranker?.[k])}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted mt">
            {fe.window}. Labels: {fe.n_labels ? `${fe.n_labels.confirmed} confirmed and ${fe.n_labels.false_alarm} false-alarm days from reviews, ${fe.n_labels.lp_flagged} loss-prevention-flagged days` : ""}; classifier {fe.classifier}. Run detection again with the re-ranker to get the new alert list.
          </p>
          <div className="row">
            <button className="btn sm" onClick={() => setPage("models")}>
              See it in Models
            </button>
          </div>
        </div>
      ) : null}
      {s.matrix.length ? (
        <TechnicalDetails title="Technical details: likely type against what teams found">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Likely type</th>
                  {Object.keys(OUTCOME_LABEL)
                    .filter((o) => o !== "open")
                    .map((o) => (
                      <th key={o} className="num">
                        {OUTCOME_LABEL[o]}
                      </th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {[...new Set(s.matrix.map((m) => m.likely_type))].map((t) => (
                  <tr key={t}>
                    <td>{TYPE_LABEL[t] ?? t}</td>
                    {Object.keys(OUTCOME_LABEL)
                      .filter((o) => o !== "open")
                      .map((o) => (
                        <td key={o} className="num">
                          {s.matrix.find((m) => m.likely_type === t && m.outcome === o)?.count ?? 0}
                        </td>
                      ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </TechnicalDetails>
      ) : null}
    </div>
  );
}
