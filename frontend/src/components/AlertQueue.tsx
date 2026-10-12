import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { Alert, AlertPage, Outcome } from "../types";
import { EmptyChipArt, EmptyState } from "./Illustrations";
import { OutcomeChip, SeverityChip, Spinner, TypeChip } from "./Layout";
import { confidenceWord, gbp, num, OUTCOME_LABEL, plain, TYPE_LABEL } from "../utils";

const PAGE = 25;

export function TriageButtons({ runId, alert, onDone }: { runId: string; alert: Alert; onDone: (outcome: Outcome) => void }) {
  const { toast, config } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const decide = async (o: Outcome) => {
    setBusy(o);
    try {
      await api.triage.decide(runId, alert.alert_id, o);
      toast(`${alert.alert_id} marked as ${OUTCOME_LABEL[o].toLowerCase()}`, "success");
      onDone(o);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="row" style={{ gap: 6 }}>
      {config.triage_outcomes.map((o) => (
        <button key={o} className={`btn sm ${alert.status === o ? "primary" : ""}`} disabled={busy !== null} onClick={() => decide(o)} aria-pressed={alert.status === o}>
          {busy === o ? <Spinner /> : null} {OUTCOME_LABEL[o]}
        </button>
      ))}
    </div>
  );
}

export function AlertDetail({ runId, alertId, answerKey, onClose, onChanged, simple = false }: { runId: string; alertId: string; answerKey: boolean; onClose: () => void; onChanged: () => void; simple?: boolean }) {
  const { openDrill, toast } = useApp();
  const [a, setA] = useState<Alert | null>(null);
  const load = useCallback(() => {
    api.runs.alert(runId, alertId, answerKey).then(setA).catch((e) => toast(errorMessage(e), "error"));
  }, [runId, alertId, answerKey, toast]);
  useEffect(load, [load]);
  if (!a) return <div className="card"><Spinner /></div>;
  return (
    <div className="card alert-detail" aria-live="polite">
      <div className="card-title">
        <h3>
          {simple ? null : <><span className="mono">{a.alert_id}</span> · </>}
          {a.store_name}
        </h3>
        <button className="btn sm link" onClick={onClose} aria-label="Close alert detail">
          ✕
        </button>
      </div>
      <div className="row" style={{ gap: 6 }}>
        <SeverityChip severity={a.severity} />
        <TypeChip type={a.likely_type} confidence={a.type_confidence} />
        <OutcomeChip outcome={a.status} />
        {a.truth_type ? <span className="chip neutral">answer key: {TYPE_LABEL[a.truth_type] ?? a.truth_type}</span> : null}
      </div>
      <dl className="kv mt">
        <dt>Item</dt>
        <dd>
          {a.sku_name} <span className="muted mono small">{a.sku_id}</span> · {a.category}
        </dd>
        <dt>When</dt>
        <dd>
          {a.start_date}
          {a.n_days > 1 ? ` to ${a.end_date} (${a.n_days} days)` : ""}
        </dd>
        <dt>At risk</dt>
        <dd>
          {num.format(a.units_at_risk)} units · <b>{gbp.format(a.value_at_risk_gbp)}</b> at cost
        </dd>
        {simple ? (
          <>
            <dt>Confidence</dt>
            <dd>
              {confidenceWord(a.p_true)} · {plain.ptrue(a.p_true)}
            </dd>
          </>
        ) : (
          <>
            <dt>How unusual</dt>
            <dd>top {Math.max(0.01, (1 - a.peak_percentile) * 100).toFixed(2)}% of days</dd>
            <dt>P(true)</dt>
            <dd>
              {Math.round(a.p_true * 100)}% · {plain.ptrue(a.p_true)}
            </dd>
          </>
        )}
        <dt>Team</dt>
        <dd>{a.warehouse_team} · {a.region}</dd>
      </dl>
      <h4 className="mt">Why it was flagged</h4>
      <ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>
        {a.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <p className="small muted">The pattern is consistent with {TYPE_LABEL[a.likely_type]?.toLowerCase() ?? "a problem"}; an investigation confirms what happened.</p>
      <h4 className="mt">Record the outcome</h4>
      <TriageButtons runId={runId} alert={a} onDone={() => { load(); onChanged(); }} />
      <div className="row mt">
        <button className="btn sm primary" onClick={() => openDrill(a.store_id, a.sku_id, a.alert_id)}>
          See the stock story →
        </button>
      </div>
    </div>
  );
}

export function AlertQueue({ runId, datasetHasTruth, simple = false }: { runId: string; datasetHasTruth: boolean; simple?: boolean }) {
  const { config, toast, selectedAlertId, setSelectedAlertId } = useApp();
  const [sev, setSev] = useState<string[]>([]);
  const [type, setType] = useState("");
  const [status, setStatus] = useState("open");
  const [sort, setSort] = useState(simple ? "plan" : "priority");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [answerKey, setAnswerKey] = useState(false);
  const [page, setPage] = useState<AlertPage | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => setOffset(0), [sev, type, status, sort, q, runId]);
  useEffect(() => {
    let stop = false;
    const t = setTimeout(() => {
      api.runs
        .alerts(runId, { severity: sev, likely_type: type ? [type] : undefined, status: status || undefined, sort, q: q || undefined, limit: PAGE, offset, answer_key: answerKey })
        .then((p) => !stop && setPage(p))
        .catch((e) => toast(errorMessage(e), "error"));
    }, 200);
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [runId, sev, type, status, sort, q, offset, answerKey, tick, toast]);
  const toggleSev = (s: string) => setSev((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  return (
    <div className={`grid ${selectedAlertId ? "grid-side narrow" : ""}`}>
      <div className="card">
        <div className="card-title">
          <h2>{simple ? "Open alerts" : "Alerts"}</h2>
          {simple ? (
            page ? <span className="small muted">{num.format(page.total)} to review, worth working first at the top · click one for the reasons</span> : null
          ) : (
            <a className="btn sm" href={api.runs.alertsCsvUrl(runId)}>
              Download all (CSV)
            </a>
          )}
        </div>
        <div className="row filters" style={{ gap: 8, marginBottom: 10 }}>
          {["critical", "high", "medium"].map((s) => (
            <button key={s} className={`toggle-chip ${sev.includes(s) ? "on" : ""}`} onClick={() => toggleSev(s)} aria-pressed={sev.includes(s)}>
              {s[0].toUpperCase() + s.slice(1)}
            </button>
          ))}
          {simple ? null : (<>
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Likely type">
            <option value="">All types</option>
            {config.anomaly_types.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t] ?? t}
              </option>
            ))}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="open">Open</option>
            <option value="reviewed">Reviewed</option>
            <option value="">All</option>
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
            <option value="priority">Most unusual first</option>
            <option value="plan">Worth working first</option>
            <option value="value">Most £ at risk</option>
            <option value="p_true">Most likely real</option>
            <option value="recent">Most recent</option>
          </select>
          </>)}
          <input type="search" placeholder="Store, SKU or alert id" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 200 }} aria-label="Search alerts" />
          {datasetHasTruth && !simple ? (
            <label className="check small">
              <input type="checkbox" checked={answerKey} onChange={(e) => setAnswerKey(e.target.checked)} /> answer key
            </label>
          ) : null}
        </div>
        {!page ? (
          <Spinner />
        ) : page.alerts.length === 0 ? (
          <EmptyState art={<EmptyChipArt />}>
            <b>No alerts match.</b>
            <div className="muted">Clear a filter, or look at reviewed alerts.</div>
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap" style={{ maxHeight: 560 }}>
              <table className="data">
                <thead>
                  <tr>
                    {simple ? null : <th>Alert</th>}
                    <th>Store · item</th>
                    {simple ? null : <th>When</th>}
                    <th>Likely type</th>
                    <th>Severity</th>
                    <th className="num">£ at risk</th>
                    {simple ? <th>Confidence</th> : <th className="num">P(true)</th>}
                    <th>Status</th>
                    {answerKey ? <th>Answer key</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {page.alerts.map((a) => (
                    <tr key={a.alert_id} className={`clickable ${selectedAlertId === a.alert_id ? "selected" : ""}`} onClick={() => setSelectedAlertId(a.alert_id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSelectedAlertId(a.alert_id)}>
                      {simple ? null : <td className="mono">{a.alert_id}</td>}
                      <td>
                        {a.store_name}
                        <div className="small muted">
                          {a.sku_name} · {a.category}
                        </div>
                      </td>
                      {simple ? null : (
                        <td className="small">
                          {a.start_date}
                          {a.n_days > 1 ? <div className="muted">{a.n_days} days</div> : null}
                        </td>
                      )}
                      <td>
                        <TypeChip type={a.likely_type} />
                      </td>
                      <td>
                        <SeverityChip severity={a.severity} />
                      </td>
                      <td className="num">{gbp.format(a.value_at_risk_gbp)}</td>
                      {simple ? <td className="small">{confidenceWord(a.p_true)}</td> : <td className="num">{Math.round(a.p_true * 100)}%</td>}
                      <td>
                        <OutcomeChip outcome={a.status} />
                      </td>
                      {answerKey ? <td className="small">{a.truth_type ? TYPE_LABEL[a.truth_type] : "–"}</td> : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row between mt small">
              <span className="muted">
                {num.format(offset + 1)}–{num.format(Math.min(offset + PAGE, page.total))} of {num.format(page.total)}
              </span>
              <div className="row" style={{ gap: 6 }}>
                <button className="btn sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  ← Previous
                </button>
                <button className="btn sm" disabled={offset + PAGE >= page.total} onClick={() => setOffset(offset + PAGE)}>
                  Next →
                </button>
              </div>
            </div>
          </>
        )}
      </div>
      {selectedAlertId ? (
        <AlertDetail
          runId={runId}
          alertId={selectedAlertId}
          answerKey={answerKey}
          simple={simple}
          onClose={() => setSelectedAlertId(null)}
          onChanged={() => setTick((t) => t + 1)}
        />
      ) : null}
    </div>
  );
}
