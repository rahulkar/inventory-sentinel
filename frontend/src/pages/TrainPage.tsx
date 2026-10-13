import { ArrowRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import { C, DetectionByTypeChart, ImportanceChart, PRCurveChart } from "../components/Charts";
import { CompeteArt, EmptyState } from "../components/Illustrations";
import { HyperparamForm } from "../components/HyperparamForm";
import { JobProgress } from "../components/JobProgress";
import { Help, Spinner } from "../components/Layout";
import { NextStep, TechnicalDetails } from "../components/TechnicalDetails";
import type { ModelMeta, ModelSummary, TrainJob } from "../types";
import { estimateSeconds, fmtDuration, isTerminal, MODEL_PLAIN, num, plain, SOURCE_LABEL } from "../utils";

const CURVE_COLORS: Record<string, string> = { zscore: "#5f6878", iforest: C.series, autoencoder: "#7a1fa2", lof: "#0e7490", ensemble: "#b45309", reranker: C.navy };

export function Leaderboard({ models, baseAp, onUse }: { models: ModelSummary[]; baseAp: number | null; onUse?: (id: string) => void }) {
  const sorted = [...models].sort((a, b) => (b.metrics.average_precision ?? -1) - (a.metrics.average_precision ?? -1));
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Method</th>
            <th className="num">
              Average precision <Help text="How well the ranking puts real problems first (1.0 = perfect). Random guessing scores only the share of days that are real problems, under 0.01 here, so 0.4 is about 60x random. Decides the winner." />
            </th>
            <th className="num">vs rule of thumb</th>
            <th className="num">
              Real in top 1,000 <Help text="Of the 1,000 most unusual days in the exam window, how many were real problems." />
            </th>
            <th className="num">
              Incidents caught <Help text="Share of hidden incidents with at least one flagged day." />
            </th>
            <th className="num">
              Value caught <Help text="Share of the money lost in hidden incidents that falls on flagged days." />
            </th>
            <th>Engine</th>
            {onUse ? <th /> : null}
          </tr>
        </thead>
        <tbody>
          {sorted.map((m, i) => {
            const x = m.metrics;
            return (
              <tr key={m.model_id} className={i === 0 && m.key !== "zscore" ? "best" : ""}>
                <td>
                  <b>{m.label}</b> {m.is_active ? <span className="chip status-done">in use</span> : null}
                  <div className="small muted">{MODEL_PLAIN[m.key]?.split(":")[0]}</div>
                </td>
                <td className="num">{x.average_precision?.toFixed(3) ?? "–"}</td>
                <td className="num">{m.key === "zscore" ? "baseline" : x.average_precision && baseAp ? `${(x.average_precision / baseAp).toFixed(1)}x` : "–"}</td>
                <td className="num">{x.precision_at_k !== null ? num.format(Math.round(x.precision_at_k * x.k)) : "–"}</td>
                <td className="num">{plain.pct(x.incident_recall)}</td>
                <td className="num">{x.value_captured_pct !== null ? `${x.value_captured_pct.toFixed(0)}%` : "–"}</td>
                <td className="small">{m.engine}</td>
                {onUse ? (
                  <td>
                    {!m.is_active ? (
                      <button className="btn sm" onClick={() => onUse(m.model_id)}>
                        Use
                      </button>
                    ) : null}
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function TrainPage() {
  const { datasets, selectedDatasetId, setSelectedDatasetId, availableModels, config, models, watchJob, jobs, toast, cancelJob, activateModel, setPage } = useApp();
  const ds = datasets.find((d) => d.id === selectedDatasetId) ?? datasets[0] ?? null;
  const [on, setOn] = useState<Record<string, boolean>>({});
  const [params, setParams] = useState<Record<string, Record<string, unknown>>>({});
  const [sample, setSample] = useState(config.default_train_sample);
  const [alertRate, setAlertRate] = useState(config.default_alert_rate);
  const [jobId, setJobId] = useState<string | null>(null);
  const [live, setLive] = useState<TrainJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [winner, setWinner] = useState<ModelMeta | null>(null);

  useEffect(() => {
    setOn(Object.fromEntries(availableModels.map((m) => [m.key, m.available && m.recommended])));
  }, [availableModels]);
  useEffect(() => setSample(config.default_train_sample), [config.default_train_sample]);
  useEffect(() => setAlertRate(config.default_alert_rate), [config.default_alert_rate]);

  const job = jobId ? jobs[jobId] ?? null : null;
  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    const tick = async () => {
      try {
        const tj = await api.train.get(jobId);
        if (!stop) setLive(tj);
      } catch {
        /* not registered yet */
      }
    };
    void tick();
    if (job && isTerminal(job.status)) {
      return () => {
        stop = true;
      };
    }
    const t = setInterval(tick, 1500);
    return () => {
      stop = true;
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, job?.status]);

  // the run to show: the live one, else the most recent run on this dataset
  const runModels = useMemo(() => {
    const mine = models.filter((m) => m.dataset_id === ds?.id && m.key !== "reranker");
    const runId = live?.job_id ?? mine[0]?.job_id;
    return mine.filter((m) => m.job_id === runId);
  }, [models, ds?.id, live?.job_id]);
  const baseAp = runModels.find((m) => m.key === "zscore")?.metrics.average_precision ?? null;
  const best = [...runModels].filter((m) => m.key !== "zscore").sort((a, b) => (b.metrics.average_precision ?? -1) - (a.metrics.average_precision ?? -1))[0] ?? null;
  const base = runModels.find((m) => m.key === "zscore") ?? null;
  useEffect(() => {
    if (!best) {
      setWinner(null);
      return;
    }
    api.models.get(best.model_id).then(setWinner).catch(() => setWinner(null));
  }, [best?.model_id]);

  const keys = Object.entries(on).filter(([, v]) => v).map(([k]) => k);
  const est = estimateSeconds("train", { modelKeys: keys, sample }, config.timing);
  const running = !!job && !["done", "failed", "cancelled"].includes(job.status);
  const start = async () => {
    if (!ds) return;
    setBusy(true);
    try {
      const j = await api.train.start({ dataset_id: ds.id, models: keys.map((k) => ({ key: k, params: params[k] ?? {} })), train_sample_size: sample, alert_rate: alertRate, exclude_lp_flagged: true, random_state: 42 });
      watchJob(j);
      setJobId(j.job_id);
      setLive(null);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };

  if (!ds) {
    return (
      <div className="card">
        <EmptyState art={<CompeteArt />}>
          <b>No data to train on yet.</b>
          <div className="muted">Create or import a dataset first.</div>
          <button className="btn primary mt" onClick={() => setPage("data")}>
            Go to Data <ArrowRight size={16} aria-hidden="true" />
          </button>
        </EmptyState>
      </div>
    );
  }

  const bx = best?.metrics;
  const realTop = (m: ModelSummary | null) => (m?.metrics.precision_at_k !== null && m ? Math.round((m.metrics.precision_at_k ?? 0) * m.metrics.k) : null);
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>2 · Train</h1>
          <p>Each method learns what a normal day looks like from history, with no labels. The last four weeks are the exam: the hidden answer key shows which method puts real problems first.</p>
        </div>
        <label className="field" style={{ width: 340 }}>
          Dataset
          <select value={ds.id} onChange={(e) => setSelectedDatasetId(e.target.value)}>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid grid-side">
        <div className="card">
          <div className="card-title">
            <h2>Methods</h2>
          </div>
          <div className="stack" style={{ gap: 8 }}>
            {availableModels.map((m) => (
              <div key={m.key} className={`model-option ${on[m.key] ? "on" : ""}`}>
                <label className="check">
                  <input type="checkbox" checked={!!on[m.key]} disabled={!m.available} onChange={(e) => setOn((o) => ({ ...o, [m.key]: e.target.checked }))} />
                  <b>{m.label}</b>
                  {m.key === "zscore" ? <span className="chip neutral">baseline</span> : null}
                </label>
                <div className="desc">{m.description}</div>
                {m.reason ? <div className="desc" style={{ color: "var(--text-2)" }}>ⓘ {m.reason}</div> : null}
                {on[m.key] ? (
                  <TechnicalDetails title="Settings">
                    <HyperparamForm params={m.params} values={params[m.key] ?? {}} onChange={(name, value) => setParams((p) => ({ ...p, [m.key]: { ...(p[m.key] ?? {}), [name]: value } }))} />
                  </TechnicalDetails>
                ) : null}
              </div>
            ))}
            <div className="form-grid single mt">
              <label className="field">
                <span>
                  History sample <Help text="Rows from the history window the methods learn from. Days flagged by loss prevention are held out." />
                </span>
                <select value={sample} onChange={(e) => setSample(Number(e.target.value))}>
                  <option value={config.quick_train_sample}>Quick: {num.format(config.quick_train_sample)} days</option>
                  <option value={config.default_train_sample}>Standard: {num.format(config.default_train_sample)} days</option>
                  <option value={500_000}>Large: 500,000 days</option>
                </select>
              </label>
              <label className="field">
                <span>
                  Alert rate · {(alertRate * 100).toFixed(1)}% <Help text="Share of days allowed to raise an alert. Lower = fewer, surer alerts." />
                </span>
                <input type="range" min={0.002} max={0.03} step={0.001} value={alertRate} onChange={(e) => setAlertRate(Number(e.target.value))} />
              </label>
            </div>
            <div className="row">
              <button className="btn primary" disabled={busy || running || !keys.length} onClick={start}>
                {busy ? <Spinner /> : null} Train {keys.length} method{keys.length === 1 ? "" : "s"}
              </button>
              <span className="small muted">takes {fmtDuration(est)}</span>
            </div>
            {job ? <JobProgress job={job} onCancel={cancelJob} /> : null}
          </div>
        </div>

        <div className="stack">
          {best && bx ? (
            <div className="winner-card">
              <div className="small muted">Winner on the exam window</div>
              <h2>{best.label}</h2>
              <div className="big">{plain.lift(bx.average_precision, baseAp) || plain.ap(bx.average_precision)}</div>
              <p className="muted" style={{ marginTop: 6 }}>
                Of the 1,000 most unusual days it picks, <b style={{ color: "#fff" }}>{num.format(realTop(best) ?? 0)}</b> are real problems
                {base ? <> against {num.format(realTop(base) ?? 0)} for the rule of thumb</> : null}. It catches {plain.pct(bx.incident_recall)} of hidden incidents{bx.value_captured_pct !== null ? <> and {bx.value_captured_pct.toFixed(0)}% of the money lost</> : null}
                {base?.metrics.value_captured_pct !== null && base ? <> (rule of thumb: {base.metrics.value_captured_pct?.toFixed(0)}%)</> : null}.
              </p>
              <div className="row mt">
                {!best.is_active ? (
                  <button className="btn" onClick={() => activateModel(best.model_id)}>
                    Use this model
                  </button>
                ) : (
                  <span className="chip status-done">in use for detection</span>
                )}
              </div>
            </div>
          ) : null}
          <div className="card">
            <div className="card-title">
              <h2>Leaderboard</h2>
              {runModels[0] ? <span className="small muted">labels: {SOURCE_LABEL[runModels[0].metrics.label_source]}</span> : null}
            </div>
            {live && live.status !== "done" ? (
              <div className="stack" style={{ gap: 6 }}>
                {live.results.map((r) => (
                  <div key={r.key} className="row between small">
                    <span>{r.label}</span>
                    <span>{r.status === "running" ? <Spinner /> : r.status === "done" ? `AP ${r.metrics?.average_precision?.toFixed(3) ?? "–"}` : r.status === "failed" ? `failed: ${r.error}` : "waiting"}</span>
                  </div>
                ))}
              </div>
            ) : null}
            {runModels.length ? (
              <Leaderboard models={runModels} baseAp={baseAp} onUse={activateModel} />
            ) : (
              <EmptyState art={<CompeteArt />}>
                <b>No models on this dataset yet.</b>
                <div className="muted">Tick the methods and press Train; all four take about a minute.</div>
              </EmptyState>
            )}
          </div>
          {runModels.length ? (
            <div className="grid grid-2">
              <div className="card">
                <div className="card-title">
                  <h3>
                    Precision vs recall <Help text="Further up and right is better: more of the real problems found while keeping alerts real." />
                  </h3>
                </div>
                <PRCurveChart curves={runModels.map((m) => ({ name: m.label, points: m.metrics.pr_curve, color: CURVE_COLORS[m.key] ?? C.muted }))} />
              </div>
              <div className="card">
                <div className="card-title">
                  <h3>What the winner catches</h3>
                </div>
                {bx ? <DetectionByTypeChart byType={bx.detection_by_type} /> : null}
              </div>
            </div>
          ) : null}
          {winner ? (
            <TechnicalDetails title={`Technical details: what drives ${winner.label}`}>
              <ImportanceChart items={winner.importances} />
              <div className="small muted">
                Thresholds: alert above {winner.thresholds.alert.toFixed(4)}, high above {winner.thresholds.high.toFixed(4)}, critical above {winner.thresholds.critical.toFixed(4)} (score units of the method). ROC-AUC {winner.metrics.roc_auc?.toFixed(3)}; {num.format(winner.metrics.n_eval_rows)} exam days ({num.format(winner.metrics.n_eval_positive)} problem days); loss-prevention-flagged days it would flag: {plain.pct(winner.metrics.lp_recall)}. {winner.notes.join(" ")}
              </div>
            </TechnicalDetails>
          ) : null}
          {best ? <NextStep title="Next: run detection" description={`Score all ${num.format(ds.n_rows)} store-SKU-days with ${best.label} and get alerts.`} cta="Go to Act" onClick={() => setPage("act")} /> : null}
        </div>
      </div>
    </div>
  );
}
