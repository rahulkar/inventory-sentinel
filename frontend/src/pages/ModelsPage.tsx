import { ArrowRight, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import { C, DetectionByTypeChart, ImportanceChart, PRCurveChart } from "../components/Charts";
import { EmptyChipArt, EmptyState } from "../components/Illustrations";
import { Help } from "../components/Layout";
import { FeatureChips, ParamList } from "../components/ModelFacts";
import { ModelExport } from "../components/ModelExport";
import { TechnicalDetails } from "../components/TechnicalDetails";
import type { ModelMeta } from "../types";
import { fmtDate, MODEL_PLAIN, num, plain, SOURCE_LABEL } from "../utils";

export function ModelsPage() {
  const { models, activateModel, deleteModel, toast, setPage } = useApp();
  const [sel, setSel] = useState<string | null>(null);
  const [detail, setDetail] = useState<ModelMeta | null>(null);
  const id = sel ?? models.find((m) => m.is_active)?.model_id ?? models[0]?.model_id ?? null;
  useEffect(() => {
    if (!id) {
      setDetail(null);
      return;
    }
    api.models.get(id).then(setDetail).catch((e) => toast(errorMessage(e), "error"));
  }, [id, models, toast]);
  if (!models.length) {
    return (
      <div className="card">
        <EmptyState art={<EmptyChipArt />}>
          <b>No models yet.</b>
          <div className="muted">Every model you train is kept here with its full metrics.</div>
          <button className="btn primary mt" onClick={() => setPage("train")}>
            Go to Train <ArrowRight size={16} aria-hidden="true" />
          </button>
        </EmptyState>
      </div>
    );
  }
  const baseFor = (dsId: string) => models.find((m) => m.key === "zscore" && m.dataset_id === dsId)?.metrics.average_precision ?? null;
  const sorted = [...models].sort((a, b) => (b.metrics.average_precision ?? -1) - (a.metrics.average_precision ?? -1));
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Models</h1>
          <p>Every trained model, best first. Average precision is measured on the exam window against a demo vendor's answer key, or loss-prevention flags and team feedback for real vendors.</p>
        </div>
      </div>
      <div className="card">
        <div className="table-wrap fill">
          <table className="data">
            <thead>
              <tr>
                <th>Model</th>
                <th>Dataset</th>
                <th className="num" style={{ whiteSpace: "normal" }}>Average precision</th>
                <th className="num" style={{ whiteSpace: "normal" }}>vs rule of thumb</th>
                <th className="num" style={{ whiteSpace: "normal" }}>Incidents caught</th>
                <th className="num" style={{ whiteSpace: "normal" }}>Value caught</th>
                <th>Engine</th>
                <th>Trained</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sorted.map((m) => {
                const b = baseFor(m.dataset_id);
                return (
                  <tr key={m.model_id} className={`clickable ${id === m.model_id ? "selected" : ""}`} onClick={() => setSel(m.model_id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSel(m.model_id)}>
                    <td>
                      <b>{m.label}</b> {m.is_active ? <span className="chip status-done">in use</span> : null}
                      <div className="small muted mono">{m.model_id}</div>
                    </td>
                    <td className="small" style={{ whiteSpace: "normal", minWidth: 160, maxWidth: 240 }}>{m.dataset_name}</td>
                    <td className="num">{m.metrics.average_precision?.toFixed(3) ?? "–"}</td>
                    <td className="num">{m.key === "zscore" ? "baseline" : b && m.metrics.average_precision ? `${(m.metrics.average_precision / b).toFixed(1)}x` : "–"}</td>
                    <td className="num">{plain.pct(m.metrics.incident_recall)}</td>
                    <td className="num">{m.metrics.value_captured_pct !== null ? `${m.metrics.value_captured_pct.toFixed(0)}%` : "–"}</td>
                    <td className="small">{m.engine}</td>
                    <td className="small">{fmtDate(m.created_at)}</td>
                    <td>
                      <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                        {!m.is_active ? (
                          <button className="btn sm" onClick={(e) => { e.stopPropagation(); void activateModel(m.model_id); }}>
                            Use
                          </button>
                        ) : null}
                        <button className="btn sm danger" aria-label={`Delete ${m.label}`} onClick={(e) => { e.stopPropagation(); if (confirm(`Delete ${m.name}?`)) void deleteModel(m.model_id); }}>
                          <Trash2 size={14} aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      {detail ? (
        <div className="card">
          <div className="card-title">
            <h2>{detail.name}</h2>
            <span className="small muted">
              {MODEL_PLAIN[detail.key]} · engine {detail.engine}
            </span>
          </div>
          <div className="grid grid-3">
            <div>
              <h3>Settings</h3>
              <ParamList modelKey={detail.key} params={detail.params} />
              <h3 className="mt">
                Signals it looks at <Help text="The detection features the method was trained on." />
              </h3>
              <FeatureChips features={detail.input_features.filter((f) => f !== "base_percentile")} />
              <h3 className="mt">Alert thresholds</h3>
              <dl className="kv">
                <dt>Alert rate</dt>
                <dd>{(detail.alert_rate * 100).toFixed(1)}% of training days</dd>
                <dt>P(true) from</dt>
                <dd>{SOURCE_LABEL[detail.calibration.source]}</dd>
                <dt>Exam window</dt>
                <dd>from {detail.test_from_date}</dd>
                <dt>Trained on</dt>
                <dd>{num.format(detail.metrics.n_train)} days</dd>
              </dl>
            </div>
            <div>
              <h3>What makes flagged days unusual</h3>
              <ImportanceChart items={detail.importances} top={8} />
            </div>
            <div>
              <h3>Incidents caught by type</h3>
              <DetectionByTypeChart byType={detail.metrics.detection_by_type} />
            </div>
          </div>
          <div className="grid grid-2 mt">
            <div>
              <h3>Precision vs recall</h3>
              <PRCurveChart curves={[{ name: detail.label, points: detail.metrics.pr_curve, color: C.series }]} height={230} />
            </div>
            <div>
              <h3>Measured on the exam window</h3>
              <dl className="kv">
                <dt>Average precision</dt>
                <dd>{detail.metrics.average_precision?.toFixed(3) ?? "–"}</dd>
                <dt>ROC-AUC</dt>
                <dd>{detail.metrics.roc_auc?.toFixed(3) ?? "–"}</dd>
                <dt>Real in top 1,000</dt>
                <dd>{detail.metrics.precision_at_k !== null ? num.format(Math.round(detail.metrics.precision_at_k * 1000)) : "–"}</dd>
                <dt>Alerts that are real</dt>
                <dd>{plain.pct(detail.metrics.precision_at_threshold)}</dd>
                <dt>Problem days flagged</dt>
                <dd>{plain.pct(detail.metrics.recall_at_threshold)}</dd>
                <dt>Incidents caught</dt>
                <dd>{plain.pct(detail.metrics.incident_recall)}</dd>
                <dt>LP-flagged days it flags</dt>
                <dd>{plain.pct(detail.metrics.lp_recall)}</dd>
                <dt>Speed</dt>
                <dd>
                  fit {detail.metrics.fit_seconds.toFixed(1)} s · scores 1M days in {detail.metrics.score_seconds_per_1m.toFixed(0)} s
                </dd>
              </dl>
              {detail.notes.map((n) => (
                <p key={n} className="small muted">
                  {n}
                </p>
              ))}
            </div>
          </div>
          {detail.feedback_eval?.base ? (
            <TechnicalDetails title="Feedback evaluation (days nobody reviewed)" open>
              <div className="small">
                Average precision {detail.feedback_eval.base.average_precision?.toFixed(3)} → <b>{detail.feedback_eval.reranker?.average_precision?.toFixed(3)}</b>; incidents caught {plain.pct(detail.feedback_eval.base.incident_recall)} → <b>{plain.pct(detail.feedback_eval.reranker?.incident_recall)}</b>; value caught {detail.feedback_eval.base.value_captured_pct?.toFixed(0)}% → <b>{detail.feedback_eval.reranker?.value_captured_pct?.toFixed(0)}%</b>.
              </div>
            </TechnicalDetails>
          ) : null}
          <div className="mt">
            <ModelExport modelId={detail.model_id} modelKey={detail.key} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
