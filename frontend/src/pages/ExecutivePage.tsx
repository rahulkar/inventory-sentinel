import { useEffect, useState, type ReactNode } from "react";
import { ArrowRight, Calendar, ChartColumnIncreasing, Check, ChevronRight, Download, Info, MapPin, Play, ShieldCheck, Tag, TriangleAlert, X } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { useApp } from "../context";
import { C } from "../components/Charts";
import { EmptyChartArt, EmptyClipboardArt, EmptyState, SinglePinArt, WarehouseArt } from "../components/Illustrations";
import { JobProgress } from "../components/JobProgress";
import { Spinner } from "../components/Layout";
import { PIPELINE_STEPS, usePipeline } from "../hooks/usePipeline";
import type { ExecutiveSummary } from "../types";
import { compactGbp, gbp, num, TYPE_HELP, TYPE_LABEL } from "../utils";

/** Executive mode home: the board overview on one screen. Three numbers, what kind of problems are open, and where the money is. */
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
  const { datasets, runs, connectors } = useApp();
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
          </div>

          <div className="exov-row2">
            <PatternsCard data={data} filters={filters} onClear={() => set({ location: "", category: "" })} />
            <ExposureCard data={data} filters={filters} onAllLocations={() => set({ location: "" })} />
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

/** "North · Womenswear": the place and category the figures are narrowed to, or "" for everything. */
function scopeName(f: Filters, data: ExecutiveSummary): string {
  const kind = f.location.slice(0, 2);
  const loc = f.location.slice(2);
  const place = kind === "r:" ? loc : kind === "s:" ? data.options.stores.find((s) => s.store_id === loc)?.store_name ?? loc : "";
  return [place, f.category ? cap(f.category) : ""].filter(Boolean).join(" · ");
}
const scopeText = (f: Filters, data: ExecutiveSummary) => (scopeName(f, data) ? ` in ${scopeName(f, data)}` : "");

function CardEmpty({ art, title, children }: { art: ReactNode; title: string; children: ReactNode }) {
  return (
    <EmptyState className="exov-empty" art={art}>
      <b>{title}</b>
      {children}
    </EmptyState>
  );
}

/** Open cases by the model's likely cause: what kind of problem the board is looking at. */
function PatternsCard({ data, filters, onClear }: { data: ExecutiveSummary; filters: Filters; onClear: () => void }) {
  const max = Math.max(1, ...data.patterns.map((p) => p.cases));
  const narrowed = Boolean(filters.location || filters.category);
  const period = PERIODS.find((p) => p.days === filters.days)?.label.toLowerCase() ?? "this period";
  return (
    <div className="card exov-card">
      <div className="exov-card-head">
        <div>
          <h2>Unusual patterns</h2>
          <p>
            {num.format(data.open_cases)} open case{data.open_cases === 1 ? "" : "s"}
            {scopeText(filters, data)} · likely cause
          </p>
        </div>
      </div>
      {data.patterns.length ? (
        <>
          <ul className="exov-bars" aria-label="Open cases by likely cause">
            {data.patterns.map((p) => (
              <li key={p.type} title={`${TYPE_HELP[p.type] ?? ""} ${money(p.revenue_gbp)} revenue at risk.`.trim()}>
                <span className="exov-bars-label">{TYPE_LABEL[p.type] ?? cap(p.type)}</span>
                <span className="exov-bars-track" aria-hidden="true">
                  <span style={{ width: `${(p.cases / max) * 100}%` }} />
                </span>
                <b>{num.format(p.cases)}</b>
              </li>
            ))}
          </ul>
          <div className="exov-caveat">
            <IconInfo />
            <span>
              <b>Suspected causes, verification required.</b> These are the model's provisional triage labels; they do not prove theft or error until a case is investigated.
            </span>
          </div>
        </>
      ) : (
        <CardEmpty art={<EmptyClipboardArt />} title="No open cases here">
          <span>
            Nothing is waiting for review{scopeText(filters, data)} for {period}.
          </span>
          {narrowed ? (
            <button className="btn sm link" onClick={onClear}>
              Show all locations and categories
            </button>
          ) : null}
        </CardEmpty>
      )}
    </div>
  );
}

/** Revenue at risk ranked by store. Ranking needs more than one store, so a single-store filter gets an explanation instead. */
function ExposureCard({ data, filters, onAllLocations }: { data: ExecutiveSummary; filters: Filters; onAllLocations: () => void }) {
  const oneStore = filters.location.startsWith("s:");
  const region = filters.location.startsWith("r:") ? filters.location.slice(2) : "";
  const n = data.top_locations.length;
  const sub = oneStore
    ? "Compares stores by revenue at risk on open cases"
    : `${n > 1 ? `Top ${n} stores` : "Stores"}${region ? ` in ${region}` : ""}${filters.category ? ` · ${cap(filters.category)}` : ""} (revenue at risk on open cases, £)`;
  return (
    <div className="card exov-card">
      <div className="exov-card-head">
        <div>
          <h2>Risk exposure by location</h2>
          <p>{sub}</p>
        </div>
        {!oneStore && n ? (
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
        ) : null}
      </div>
      {oneStore ? (
        <CardEmpty art={<SinglePinArt />} title="One store selected">
          <span>
            This view ranks locations against each other. {scopeName(filters, data)} has {money(data.revenue_at_risk_gbp)} at risk on {num.format(data.open_cases)} open case
            {data.open_cases === 1 ? "" : "s"}.
          </span>
          <button className="btn sm link" onClick={onAllLocations}>
            Compare all locations
          </button>
        </CardEmpty>
      ) : n ? (
        <ResponsiveContainer width="100%" height={n * 36 + 40}>
          <BarChart data={data.top_locations} layout="vertical" margin={{ top: 0, right: 56, left: 0, bottom: 4 }}>
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
        <CardEmpty art={<EmptyChartArt />} title="No revenue at risk here">
          <span>No store has open cases{scopeText(filters, data)} in this period, so there is nothing to rank.</span>
        </CardEmpty>
      )}
    </div>
  );
}

const KPI_ICON = { size: 34, strokeWidth: 1.7, "aria-hidden": true } as const;
const FILTER_ICON = { size: 16, "aria-hidden": true } as const;
const IconAlert = ({ color }: { color: string }) => <TriangleAlert {...KPI_ICON} color={color} />;
const IconShield = () => <ShieldCheck {...KPI_ICON} color="#1a9fe0" />;
const IconBars = () => <ChartColumnIncreasing {...KPI_ICON} color="#1a9fe0" />;
const IconCalendar = () => <Calendar {...FILTER_ICON} />;
const IconPin = () => <MapPin {...FILTER_ICON} />;
const IconTag = () => <Tag {...FILTER_ICON} />;
const IconExport = () => <Download {...FILTER_ICON} />;
const IconInfo = () => <Info size={15} aria-hidden="true" />;

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
                  {state === "done" ? <Check size={15} strokeWidth={3} /> : state === "failed" ? <X size={15} strokeWidth={3} /> : i + 1}
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
                <Play size={16} fill="currentColor" aria-hidden="true" /> Run the whole pipeline
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
                  Go to Data <ChevronRight size={14} aria-hidden="true" /> Connect <ArrowRight size={16} aria-hidden="true" />
                </button>
              </div>
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}
