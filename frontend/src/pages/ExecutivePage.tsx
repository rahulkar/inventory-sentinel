import { useEffect, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { useApp } from "../context";
import { C } from "../components/Charts";
import { WarehouseArt } from "../components/Illustrations";
import { JobProgress } from "../components/JobProgress";
import { Spinner } from "../components/Layout";
import { PIPELINE_STEPS, usePipeline } from "../hooks/usePipeline";
import type { ExecTrend, ExecutiveSummary } from "../types";
import { compactGbp, gbp, num } from "../utils";

/** Executive mode home: the board overview on one screen. Four numbers, weekly trends, where the money is, how fast cases close. */
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

const FILTER_KEY = "sentinel.execFilters";
const PERIODS = [
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
  { days: 0, label: "All data" },
];
const SERIES = ["#1a9fe0", "#2f3a4a", "#9b6cf0"]; // sky, charcoal, violet
const RED = "#d03b3b";
const AMBER = "#e59a00";

type Filters = { days: number; location: string; category: string }; // location: "" | "r:<region>" | "s:<store_id>"

function loadFilters(): Filters {
  try {
    const f = JSON.parse(window.localStorage.getItem(FILTER_KEY) ?? "null");
    if (f && typeof f.days === "number") return { days: f.days, location: String(f.location ?? ""), category: String(f.category ?? "") };
  } catch {
    /* private window or bad JSON: use the defaults */
  }
  return { days: 90, location: "", category: "" };
}

/** £1.11m / £27.5k: one more digit than compactGbp, for the board figures. */
function money(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e6) return `£${(v / 1e6).toFixed(2)}m`;
  if (a >= 1e3) return `£${(v / 1e3).toFixed(1)}k`;
  return `£${Math.round(v)}`;
}
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const dayLabel = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

function ExecAnswer({ onRerun }: { onRerun?: (connectorId: string) => void }) {
  const { setPage, datasets, runs, connectors } = useApp();
  const conn = connectors.find((c) => c.enabled) ?? null;
  const run = runs.find((r) => r.model_in_use) ?? runs[0] ?? null;
  const runId = run?.run_id ?? null;
  const ds = datasets.find((x) => x.id === run?.dataset_id) ?? datasets[0];
  const [filters, setFilters] = useState<Filters>(loadFilters);
  const [data, setData] = useState<ExecutiveSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(FILTER_KEY, JSON.stringify(filters));
    } catch {
      /* the choice lasts for this tab only */
    }
    if (!runId) return;
    let stop = false;
    const kind = filters.location.slice(0, 2);
    const loc = filters.location.slice(2);
    setLoading(true);
    api.runs
      .executive(runId, { days: filters.days, region: kind === "r:" ? loc : null, store_id: kind === "s:" ? loc : null, category: filters.category || null })
      .then((d) => {
        if (stop) return;
        setData(d);
        setError(null);
      })
      .catch((e) => !stop && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !stop && setLoading(false));
    return () => {
      stop = true;
    };
  }, [runId, filters]);

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));
  const source = ds?.kind === "connector" ? String(ds.params?.connector_name ?? "Vendor data") : ds?.kind === "synthetic" ? "Synthetic demo data" : "Uploaded data";
  const riskColor = data && data.revenue_at_risk_gbp > data.threshold_gbp ? RED : AMBER;

  return (
    <div className="exov">
      <div className="exov-head">
        <div className="exov-title">
          <div className="exov-title-row">
            <h1>Executive overview</h1>
            <span className="exov-badge">{source}</span>
          </div>
          <p>Inventory risk, business impact and resolution{data ? ` · data to ${dayLabel(data.period.end)}` : ""}</p>
        </div>
        <div className="exov-filters">
          <label className="exov-filter">
            <IconCalendar />
            <select aria-label="Period" value={filters.days} onChange={(e) => set({ days: Number(e.target.value) })}>
              {PERIODS.map((p) => (
                <option key={p.days} value={p.days}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="exov-filter">
            <IconPin />
            <select aria-label="Location" value={filters.location} onChange={(e) => set({ location: e.target.value })}>
              <option value="">All locations</option>
              {data?.options.regions.length ? (
                <optgroup label="Regions">
                  {data.options.regions.map((r) => (
                    <option key={r} value={`r:${r}`}>
                      {r}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              {data?.options.stores.length ? (
                <optgroup label="Stores">
                  {data.options.stores.map((s) => (
                    <option key={s.store_id} value={`s:${s.store_id}`}>
                      {s.store_name}
                    </option>
                  ))}
                </optgroup>
              ) : null}
            </select>
          </label>
          <label className="exov-filter">
            <IconTag />
            <select aria-label="Category" value={filters.category} onChange={(e) => set({ category: e.target.value })}>
              <option value="">All categories</option>
              {data?.options.categories.map((c) => (
                <option key={c} value={c}>
                  {cap(c)}
                </option>
              ))}
            </select>
          </label>
          <button className="exov-export" onClick={() => window.print()} disabled={!data}>
            <IconExport />
            Export board report
          </button>
        </div>
      </div>

      {error ? <div className="callout error">Could not load the overview: {error}</div> : null}
      {!data ? (
        error ? null : (
          <div className="card">
            <Spinner /> Loading the latest results…
          </div>
        )
      ) : (
        <div className={`exov-body ${loading ? "is-loading" : ""}`} aria-busy={loading}>
          <div className="exov-kpis">
            <Kpi
              icon={<IconAlert color={riskColor} />}
              label="Revenue at risk"
              value={<span style={{ color: riskColor }}>{money(data.revenue_at_risk_gbp)}</span>}
              sub={`Across ${num.format(data.open_cases)} open cases`}
              title={`Units at risk × selling price on open cases; red above ${gbp.format(data.threshold_gbp)}, amber below. Valued at cost: ${gbp.format(data.value_at_risk_gbp)}.`}
            />
            <Kpi icon={<IconShield />} label="Verified loss prevented" value={money(data.loss_prevented_gbp)} sub="Closed cases only" title={`Retail value of the ${num.format(data.closed_cases)} reviewed cases in this selection that were real problems`} />
            <Kpi
              icon={<IconBars />}
              label="Inventory accuracy"
              value={data.inventory_accuracy_pct === null ? "–" : `${data.inventory_accuracy_pct.toFixed(1)}%`}
              sub={
                data.accuracy_delta_pp === null ? (
                  "Counts within 2% of the books"
                ) : (
                  <b className={data.accuracy_delta_pp >= 0 ? "exov-up" : "exov-down"}>
                    {data.accuracy_delta_pp >= 0 ? "+" : ""}
                    {data.accuracy_delta_pp.toFixed(1)} pp vs prior period
                  </b>
                )
              }
              title="Share of store-item-days whose count matched the expected stock within 1 unit or 2%"
            />
            <Kpi icon={<IconClock />} label="Resolution within SLA" value={data.sla_within_pct === null ? "–" : `${Math.round(data.sla_within_pct)}%`} sub={`Target ${data.sla_target_pct}%`} title={`Closed cases resolved within ${data.sla_days} days of the last flagged day`} />
          </div>

          <div className="exov-row2">
            <TrendCard title="Anomaly trend by store" sub={filters.location.startsWith("s:") ? "Weekly new alerts • selected store" : "Weekly new alerts • top stores by revenue at risk"} trend={data.store_trend} kind="line" />
            <TrendCard title="Anomaly trend by category" sub={filters.category ? "Weekly new alerts • selected category" : "Weekly new alerts • top categories by revenue at risk"} trend={data.category_trend} kind="bar" />
          </div>

          <div className="exov-row3">
            <div className="card exov-card">
              <div className="exov-card-head">
                <div>
                  <h2>Risk exposure by location</h2>
                  <p>{data.top_locations.length > 1 ? `Top ${data.top_locations.length} stores` : "Store"} (revenue at risk on open cases, £)</p>
                </div>
                <div className="exov-legend">
                  <span>
                    <i style={{ background: RED }} />
                    Above {compactGbp(data.threshold_gbp)}
                  </span>
                  <span>
                    <i style={{ background: AMBER }} />
                    Below {compactGbp(data.threshold_gbp)}
                  </span>
                </div>
              </div>
              {data.top_locations.length ? (
                <ResponsiveContainer width="100%" height={data.top_locations.length * 36 + 40}>
                  <BarChart data={data.top_locations} layout="vertical" margin={{ top: 0, right: 64, left: 0, bottom: 4 }}>
                    <CartesianGrid horizontal={false} stroke={C.grid} />
                    <XAxis type="number" tick={tick} axisLine={axisLine} tickLine={false} tickFormatter={(v: number) => compactGbp(v)} />
                    <YAxis type="category" dataKey="label" width={170} tick={tick} axisLine={axisLine} tickLine={false} />
                    <Tooltip cursor={{ fill: "rgba(26,159,224,0.06)" }} formatter={(v) => [gbp.format(Number(v)), "Revenue at risk"]} />
                    <Bar dataKey="value_gbp" barSize={16} radius={[0, 3, 3, 0]} isAnimationActive={false}>
                      {data.top_locations.map((l) => (
                        <Cell key={l.store_id} fill={l.value_gbp > data.threshold_gbp ? RED : AMBER} />
                      ))}
                      <LabelList dataKey="value_gbp" position="right" formatter={(v) => money(Number(v))} style={{ fontSize: 12, fontWeight: 700, fill: "#121826" }} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="muted">No open cases in this selection.</p>
              )}
            </div>

            <div className="card exov-card exov-res">
              <h2>Resolution performance</h2>
              <div className="exov-overdue">
                <IconAlert color={RED} />
                <div>
                  <b>{num.format(data.overdue_cases)}</b>
                  <span>Overdue cases</span>
                </div>
              </div>
              <p className="small muted">Critical and high cases still open {data.sla_days}+ days after the last flagged day.</p>
              {data.sla_within_pct === null ? (
                <p className="muted">No closed cases in this period yet.</p>
              ) : (
                <div className="exov-sla">
                  <div className="exov-sla-row">
                    <b>{Math.round(data.sla_within_pct)}% within SLA</b>
                    <span className="muted">Target {data.sla_target_pct}%</span>
                  </div>
                  <div className="exov-meter" role="img" aria-label={`${Math.round(data.sla_within_pct)}% of closed cases resolved within SLA, target ${data.sla_target_pct}%`}>
                    <span style={{ width: `${Math.min(100, data.sla_within_pct)}%` }} />
                    <i style={{ left: `${data.sla_target_pct}%` }} />
                  </div>
                </div>
              )}
              <button className="exov-outline" onClick={() => setPage("alerts")}>
                View resolutions
              </button>
            </div>
          </div>

          <div className="exov-foot">
            <span>
              <IconInfo /> Anomalies indicate risk; causes require verification.
            </span>
            <span className="small muted">
              Model in use: {run?.model_label ?? "–"} · {source}, {dayLabel(data.period.start)} – {dayLabel(data.period.end)}
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
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function Kpi({ icon, label, value, sub, title }: { icon: ReactNode; label: string; value: ReactNode; sub: ReactNode; title?: string }) {
  return (
    <div className="card exov-kpi" title={title}>
      <span className="exov-kpi-icon">{icon}</span>
      <div>
        <div className="exov-kpi-label">{label}</div>
        <div className="exov-kpi-value">{value}</div>
        <div className="exov-kpi-sub">{sub}</div>
      </div>
    </div>
  );
}

const tick = { fill: C.text, fontSize: 12 };
const axisLine = { stroke: C.grid };
const yLabel = { value: "New alerts", angle: -90, position: "insideLeft" as const, style: { fontSize: 11, fill: C.textMuted, textAnchor: "middle" as const } };

function TrendCard({ title, sub, trend, kind }: { title: string; sub: string; trend: ExecTrend; kind: "line" | "bar" }) {
  const rows = trend.rows.map((r) => ({ ...r, label: dayLabel(r.week) }));
  const labels = rows.length <= 6; // value labels on every point only while they stay readable
  const valueLabel = { fontSize: 11, fontWeight: 700, fill: C.text };
  return (
    <div className="card exov-card">
      <div className="exov-card-head">
        <div>
          <h2>{title}</h2>
          <p>{sub}</p>
        </div>
        <div className="exov-legend">
          {trend.series.map((s, i) => (
            <span key={s}>
              <i className="round" style={{ background: SERIES[i] }} />
              {cap(s)}
            </span>
          ))}
        </div>
      </div>
      {trend.series.length ? (
        <ResponsiveContainer width="100%" height={210}>
          {kind === "line" ? (
            <LineChart data={rows} margin={{ top: 18, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={C.grid} />
              <XAxis dataKey="label" tick={tick} axisLine={axisLine} tickLine={false} />
              <YAxis allowDecimals={false} tick={tick} axisLine={false} tickLine={false} width={44} label={yLabel} />
              <Tooltip />
              {trend.series.map((s, i) => (
                <Line key={s} name={cap(s)} dataKey={(r: Record<string, number>) => r[s]} stroke={SERIES[i]} strokeWidth={2} dot={{ r: 3.5, fill: SERIES[i] }} isAnimationActive={false}>
                  {labels ? <LabelList position="top" offset={8} style={valueLabel} /> : null}
                </Line>
              ))}
            </LineChart>
          ) : (
            <BarChart data={rows} margin={{ top: 18, right: 8, left: 0, bottom: 0 }} barGap={3}>
              <CartesianGrid vertical={false} stroke={C.grid} />
              <XAxis dataKey="label" tick={tick} axisLine={axisLine} tickLine={false} />
              <YAxis allowDecimals={false} tick={tick} axisLine={false} tickLine={false} width={44} label={yLabel} />
              <Tooltip cursor={{ fill: "rgba(26,159,224,0.06)" }} />
              {trend.series.map((s, i) => (
                <Bar key={s} name={cap(s)} dataKey={(r: Record<string, number>) => r[s]} fill={SERIES[i]} maxBarSize={22} isAnimationActive={false}>
                  {labels ? <LabelList position="top" style={valueLabel} /> : null}
                </Bar>
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      ) : (
        <p className="muted">No new alerts in this selection.</p>
      )}
      <p className="exov-note">New alerts are different from currently open cases.</p>
    </div>
  );
}

function Svg({ children, size = 34, color = "currentColor" }: { children: ReactNode; size?: number; color?: string }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke={color} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}
const IconAlert = ({ color }: { color: string }) => (
  <Svg color={color}>
    <path d="M12 3 2 20h20L12 3z" />
    <path d="M12 10v4.5M12 17.2v.1" />
  </Svg>
);
const IconShield = () => (
  <Svg color="#1a9fe0">
    <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6L12 3z" />
    <path d="m8.8 12 2.3 2.3 4.3-4.6" />
  </Svg>
);
const IconBars = () => (
  <Svg color="#1a9fe0">
    <path d="M6 20v-6M10 20V10M14 20V7M18 20V4" strokeWidth={3} />
  </Svg>
);
const IconClock = () => (
  <Svg color="#121826">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3.5 2" />
  </Svg>
);
const IconCalendar = () => (
  <Svg size={16}>
    <rect x="3.5" y="5" width="17" height="15" rx="2" />
    <path d="M3.5 10h17M8 3v4M16 3v4" />
  </Svg>
);
const IconPin = () => (
  <Svg size={16}>
    <path d="M12 21s-6.5-6.1-6.5-11a6.5 6.5 0 0 1 13 0c0 4.9-6.5 11-6.5 11z" />
    <circle cx="12" cy="10" r="2.3" />
  </Svg>
);
const IconTag = () => (
  <Svg size={16}>
    <path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1 1 0 0 1 0 1.4l-7.3 7.3a1 1 0 0 1-1.4 0l-8.3-8.3z" />
    <circle cx="8" cy="8" r="1.4" />
  </Svg>
);
const IconExport = () => (
  <Svg size={16}>
    <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M4.5 19.5h15" />
  </Svg>
);
const IconInfo = () => (
  <Svg size={15}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.8v.1" />
  </Svg>
);

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
