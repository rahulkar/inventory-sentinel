import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { Dashboard, TopRow } from "../types";
import { MetricBarChart, SEVERITY_COLOR, TrendChart } from "./Charts";
import { Help, Spinner, StatCard } from "./Layout";
import { TechnicalDetails } from "./TechnicalDetails";
import { gbp, num, plain, titleCase, TYPE_LABEL } from "../utils";

/** Store x category grid of £ at risk; an accessible table underneath carries the same numbers. */
export function HeatmapGrid({ d, onCell, maxRows = 20, compact = false }: { d: Dashboard; onCell?: (storeId: string, category: string) => void; maxRows?: number; compact?: boolean }) {
  const [metric, setMetric] = useState<"value_gbp" | "alerts">("value_gbp");
  const stores = useMemo(() => {
    const tot: Record<string, { name: string; v: number }> = {};
    for (const c of d.heatmap) {
      tot[c.store_id] = tot[c.store_id] ?? { name: c.store_name, v: 0 };
      tot[c.store_id].v += c[metric];
    }
    return Object.entries(tot)
      .sort((a, b) => b[1].v - a[1].v)
      .slice(0, maxRows);
  }, [d.heatmap, metric, maxRows]);
  const cats = d.categories.filter((c) => d.heatmap.some((h) => h.category === c));
  const cell = (s: string, c: string) => d.heatmap.find((h) => h.store_id === s && h.category === c);
  const max = Math.max(1, ...d.heatmap.map((h) => h[metric]));
  const shade = (v: number) => {
    if (!v) return { background: "var(--surface-2)", color: "var(--text-3)" };
    const t = Math.sqrt(v / max);
    const steps = ["#e3ecf8", "#b9d3f3", "#86b6ef", "#4f93e2", "#2269c0", "#1c5cab", "#104281"];
    const i = Math.min(steps.length - 1, Math.floor(t * steps.length));
    return { background: steps[i], color: i >= 4 ? "#fff" : "#121826" };
  };
  return (
    <div>
      <div className="row between" style={{ marginBottom: 8 }}>
        <span className="small muted">Top {maxRows} stores by {metric === "alerts" ? "alerts" : "£ at risk"}; darker = more.</span>
        {compact ? null : (
        <div className="row" style={{ gap: 6 }}>
          <button className={`toggle-chip ${metric === "value_gbp" ? "on" : ""}`} onClick={() => setMetric("value_gbp")}>
            £ at risk
          </button>
          <button className={`toggle-chip ${metric === "alerts" ? "on" : ""}`} onClick={() => setMetric("alerts")}>
            Alerts
          </button>
        </div>
        )}
      </div>
      <div className="heatmap" style={{ gridTemplateColumns: `minmax(130px, 200px) repeat(${cats.length}, minmax(44px, 1fr))` }} role="table" aria-label="Store by category heatmap">
        <div role="columnheader" />
        {cats.map((c) => (
          <div key={c} className="hm-head" role="columnheader">
            {titleCase(c)}
          </div>
        ))}
        {stores.map(([sid, info]) => (
          <div key={sid} style={{ display: "contents" }} role="row">
            <div className="hm-row" role="rowheader" title={info.name}>
              {info.name}
            </div>
            {cats.map((c) => {
              const v = cell(sid, c)?.[metric] ?? 0;
              return (
                <button key={c} className="hm-cell" style={shade(v)} onClick={() => onCell?.(sid, c)} title={`${info.name} · ${titleCase(c)}: ${metric === "alerts" ? `${v} alerts` : gbp.format(v)}`} aria-label={`${info.name}, ${c}: ${metric === "alerts" ? `${v} alerts` : gbp.format(v)}`}>
                  {v ? (metric === "alerts" ? v : v >= 1000 ? `${Math.round(v / 1000)}k` : Math.round(v)) : ""}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function TopList({ title, rows, money = true }: { title: string; rows: TopRow[]; money?: boolean }) {
  return (
    <div className="card">
      <div className="card-title">
        <h3>{title}</h3>
      </div>
      <MetricBarChart rows={rows.slice(0, 8).map((r) => ({ label: r.label, value: money ? r.value_gbp : r.alerts }))} metric={money ? "£ at risk" : "Alerts"} format={(v) => (money ? gbp.format(v) : num.format(v))} />
    </div>
  );
}

export function AnomalyDashboard({ runId }: { runId: string }) {
  const { toast, setActTab, setSelectedAlertId } = useApp();
  const [d, setD] = useState<Dashboard | null>(null);
  const [mode, setMode] = useState<"severity" | "type">("severity");
  useEffect(() => {
    setD(null);
    api.runs.dashboard(runId).then(setD).catch((e) => toast(errorMessage(e), "error"));
  }, [runId, toast]);
  if (!d) return <Spinner />;
  const k = d.run.kpis;
  const ev = d.run.evaluation;
  return (
    <div className="stack">
      <div className="grid grid-4">
        <StatCard label="Alerts" value={num.format(k.incidents)} sub={`${num.format(k.flagged_rows)} flagged days (${k.pct_rows_flagged.toFixed(2)}% of ${num.format(k.rows_scored)})`} />
        <StatCard label="Stock value at risk" value={gbp.format(k.value_at_risk_gbp)} sub="valued at cost, all alerts" />
        <StatCard label="Critical alerts" value={num.format(k.by_severity.critical ?? 0)} sub={`${num.format(k.by_severity.high ?? 0)} high · ${num.format(k.by_severity.medium ?? 0)} medium`} />
        <StatCard label="Stores affected" value={num.format(k.stores_affected)} sub={ev ? `exam window: ${plain.recall(ev.incident_recall)}, ${plain.pct(ev.alert_precision)} of alerts real` : d.run.model_label} />
      </div>
      <div className="card">
        <div className="card-title">
          <h2>
            Anomalies over time <Help text="Flagged store-SKU-days per day, stacked; the tooltip adds the £ at risk." />
          </h2>
          <div className="row" style={{ gap: 6 }}>
            <button className={`toggle-chip ${mode === "severity" ? "on" : ""}`} onClick={() => setMode("severity")}>
              By severity
            </button>
            <button className={`toggle-chip ${mode === "type" ? "on" : ""}`} onClick={() => setMode("type")}>
              By likely type
            </button>
          </div>
        </div>
        <TrendChart rows={d.trend} mode={mode} types={d.types} />
      </div>
      <div className="card">
        <div className="card-title">
          <h2>Where it happens: store x category</h2>
        </div>
        <HeatmapGrid
          d={d}
          onCell={() => {
            setSelectedAlertId(null);
            setActTab("alerts");
          }}
        />
      </div>
      <div className="grid grid-3">
        <TopList title="Stores with most £ at risk" rows={d.top_stores} />
        <TopList title="Warehouse teams" rows={d.top_teams} />
        <TopList title="Categories" rows={d.by_category.map((r) => ({ ...r, label: titleCase(r.label) }))} />
      </div>
      <TechnicalDetails title="Technical details: run and evaluation">
        <dl className="kv">
          <dt>Model</dt>
          <dd>{d.run.model_name}</dd>
          <dt>Thresholds</dt>
          <dd>
            alert ≥ {d.run.thresholds.alert.toFixed(4)}, high ≥ {d.run.thresholds.high.toFixed(4)}, critical ≥ {d.run.thresholds.critical.toFixed(4)}
          </dd>
          <dt>Scored in</dt>
          <dd>{d.run.seconds?.toFixed(1)} s</dd>
          <dt>Likely types</dt>
          <dd>{Object.entries(k.by_type).map(([t, n]) => `${TYPE_LABEL[t] ?? t} ${n}`).join(" · ")}</dd>
          {ev ? (
            <>
              <dt>Exam window</dt>
              <dd>
                {ev.window}: incidents caught {plain.pct(ev.incident_recall)}, alerts real {plain.pct(ev.alert_precision)}, value caught {ev.value_captured_pct?.toFixed(0)}%, likely type right {plain.pct(ev.type_accuracy)} (synthetic answer key)
              </dd>
            </>
          ) : null}
        </dl>
        <div className="legend mt">
          {Object.entries(SEVERITY_COLOR).map(([s, c]) => (
            <span key={s}>
              <span className="sw" style={{ background: c }} />
              {s}
            </span>
          ))}
        </div>
      </TechnicalDetails>
    </div>
  );
}
