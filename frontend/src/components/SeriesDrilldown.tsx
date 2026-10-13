import { useEffect, useState } from "react";
import { SopChecklist } from "./SopChecklist";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { SeriesMatch, SeriesResponse } from "../types";
import { SeriesChart } from "./Charts";
import { DrilldownArt, EmptyState } from "./Illustrations";
import { OutcomeChip, SeverityChip, Spinner, StatCard, TypeChip } from "./Layout";
import { TriageButtons } from "./AlertQueue";
import { gbp, gbp2, num, OUTCOME_LABEL, TYPE_LABEL } from "../utils";

export function SeriesDrilldown({ runId, datasetHasTruth }: { runId: string; datasetHasTruth: boolean }) {
  const { drill, openDrill, toast, selectedAlertId } = useApp();
  const [q, setQ] = useState("");
  const [matches, setMatches] = useState<SeriesMatch[]>([]);
  const [s, setS] = useState<SeriesResponse | null>(null);
  const [answerKey, setAnswerKey] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!q.trim()) {
      setMatches([]);
      return;
    }
    let stale = false;
    const t = setTimeout(() => {
      api.runs
        .search(runId, q)
        .then((m) => !stale && setMatches(m))
        .catch(() => !stale && setMatches([]));
    }, 250);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [q, runId]);
  useEffect(() => {
    if (!drill) return;
    setS(null);
    let stale = false;
    api.runs
      .series(runId, drill.storeId, drill.skuId, answerKey)
      .then((x) => !stale && setS(x))
      .catch((e) => !stale && toast(errorMessage(e), "error"));
    return () => {
      stale = true;
    };
  }, [runId, drill, answerKey, tick, toast]);
  const gap = s ? s.points.reduce((a, p) => a + p.variance_units, 0) : 0;
  const flagged = s ? s.points.filter((p) => p.severity > 0).length : 0;
  const days = s ? Object.entries(s.flagged_reasons) : [];
  const SEV: Record<string, number> = { critical: 3, high: 2, medium: 1 };
  const focus = s ? s.alerts.find((a) => a.alert_id === selectedAlertId) ?? [...s.alerts].sort((a, b) => (SEV[b.severity] ?? 0) - (SEV[a.severity] ?? 0) || b.value_at_risk_gbp - a.value_at_risk_gbp)[0] ?? null : null;
  return (
    <div className="stack">
      <div className="card">
        <div className="card-title">
          <h2>Find a store and item</h2>
          {datasetHasTruth ? (
            <label className="check small">
              <input type="checkbox" checked={answerKey} onChange={(e) => setAnswerKey(e.target.checked)} /> show the demo answer key
            </label>
          ) : null}
        </div>
        <input type="search" placeholder="e.g. S012 mascara, Leeds beauty, K00042" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search store and item" />
        {matches.length ? (
          <div className="list mt">
            {matches.map((m) => (
              <div key={`${m.store_id}|${m.sku_id}`} className="list-item" onClick={() => { openDrill(m.store_id, m.sku_id); setQ(""); }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="title">
                    {m.store_name} · {m.sku_name}
                  </div>
                  <div className="meta">
                    {m.store_id} / {m.sku_id} · {m.category}
                  </div>
                </div>
                {m.n_alerts ? <span className="chip primary">{m.n_alerts} alerts</span> : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
      {!drill ? (
        <div className="card">
          <EmptyState art={<DrilldownArt />}>
            <b>Pick an alert or search for an item.</b>
            <div className="muted">You will see expected against counted stock day by day, the flagged days and why they were flagged.</div>
          </EmptyState>
        </div>
      ) : !s ? (
        <Spinner />
      ) : (
        <>
          <div className="grid grid-4">
            <StatCard label="Store" value={s.store_name} sub={s.store_id} />
            <StatCard label="Item" value={s.sku_name} sub={`${s.sku_id} · ${s.category} · ${gbp2.format(s.unit_cost)} each`} />
            <StatCard label="Stock missing over the period" value={`${num.format(gap)} units`} sub={`${gbp.format(Math.max(gap, 0) * s.unit_cost)} at cost`} />
            <StatCard label="Flagged days" value={num.format(flagged)} sub={`${s.alerts.length} alert${s.alerts.length === 1 ? "" : "s"}`} />
          </div>
          <div className="card">
            <div className="card-title">
              <h2>The stock story</h2>
              <span className="small muted">shaded = flagged days · purple diamond = loss-prevention flag{answerKey ? " · red cross = answer key" : ""}</span>
            </div>
            <SeriesChart points={s.points} showTruth={answerKey} height={340} />
          </div>
          <div className="grid grid-2">
            <div className="card">
              <div className="card-title">
                <h3>Alerts on this item</h3>
              </div>
              {s.alerts.length ? (
                <div className="stack" style={{ gap: 12 }}>
                  {s.alerts.map((a) => (
                    <div key={a.alert_id} className="alert-row">
                      <div className="row" style={{ gap: 6 }}>
                        <span className="mono small">{a.alert_id}</span>
                        <SeverityChip severity={a.severity} />
                        <TypeChip type={a.likely_type} confidence={a.type_confidence} />
                        <OutcomeChip outcome={a.status} />
                        {a.truth_type ? <span className="chip neutral">answer key: {TYPE_LABEL[a.truth_type]}</span> : null}
                      </div>
                      <div className="small mt">
                        {a.start_date}
                        {a.n_days > 1 ? ` to ${a.end_date}` : ""} · {gbp.format(a.value_at_risk_gbp)} at risk · P(true) {Math.round(a.p_true * 100)}%
                      </div>
                      <div className="mt">
                        <TriageButtons runId={runId} alert={a} onDone={() => setTick((t) => t + 1)} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted small">No alert on this item in this run.</p>
              )}
            </div>
            <div className="card">
              <div className="card-title">
                <h3>Why each flagged day stood out</h3>
              </div>
              {days.length ? (
                <div className="stack small" style={{ gap: 8 }}>
                  {days.map(([day, rs]) => (
                    <div key={day}>
                      <b>{day}</b>
                      <ul style={{ margin: "2px 0 0", paddingLeft: 18 }}>
                        {rs.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted small">No day on this item was flagged.</p>
              )}
              {s.triage.length ? (
                <div className="small mt">
                  <b>Team decisions:</b> {s.triage.map((t) => `${t.start_date} ${OUTCOME_LABEL[t.outcome]}${t.source === "simulated" ? " (simulated)" : t.source === "vendor_task" ? " (from a vendor task)" : ""}`).join(" · ")}
                </div>
              ) : null}
            </div>
          </div>
          {focus ? (
            <div className="card">
              <div className="card-title">
                <h2>What to do about {focus.alert_id}</h2>
                <span className="small muted">from the standard operating procedures</span>
              </div>
              <SopChecklist key={focus.alert_id} runId={runId} alertId={focus.alert_id} />
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
