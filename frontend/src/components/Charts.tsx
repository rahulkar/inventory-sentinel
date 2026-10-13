import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useMediaQuery } from "../hooks/useJob";
import type { HistBin, ImportanceItem, PlanCurvePoint, PRPoint, SeriesPoint, TrendRow, TriageGroup } from "../types";
import { featureLabel, gbp, num, SEVERITY_LABEL, TYPE_LABEL } from "../utils";

// Palette: one blue series hue, a fixed severity ramp (critical red, high orange, medium amber) and a categorical
// set for anomaly types; all marks are >= 3:1 against white, and text never relies on colour alone.
export const C = {
  series: "#2a78d6",
  navy: "#104281",
  muted: "#8d97a8",
  good: "#0a800a",
  critical: "#b42318",
  high: "#c2410c",
  medium: "#d99a00",
  grid: "#e6e8ee",
  text: "#4b5363",
  textMuted: "#5f6878",
};

export const SEVERITY_COLOR: Record<string, string> = { critical: C.critical, high: C.high, medium: C.medium };
export const TYPE_COLOR: Record<string, string> = {
  theft_external: "#b42318",
  theft_internal: "#7a1fa2",
  scan_fraud: "#c2410c",
  counting_error: "#2a78d6",
  receiving_error: "#0e7490",
  data_entry_error: "#5f6878",
  velocity_shift: "#0a800a",
  unclear: "#8d97a8",
};

const tick = { fill: C.text, fontSize: 12 };
const axisLine = { stroke: C.grid };

function Box({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ background: "#fff", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", fontSize: 12, color: "var(--text)", boxShadow: "var(--shadow)" }}>
      {children}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type TipProps = { active?: boolean; payload?: ReadonlyArray<any>; label?: unknown };

const shortDate = (d: string) => {
  const dt = new Date(d);
  return Number.isNaN(dt.getTime()) ? d : dt.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
};

export function HistogramChart({ bins, height = 220, label = "Days", unit = "" }: { bins: HistBin[]; height?: number; label?: string; unit?: string }) {
  if (!bins.length) return <div className="empty">No distribution yet.</div>;
  const data = bins.map((b) => ({ x: `${num.format(b.bin_start)}${unit}`, count: b.count, start: b.bin_start, end: b.bin_end }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -4, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey="x" tick={tick} axisLine={axisLine} tickLine={false} interval="preserveStartEnd" minTickGap={28} />
        <YAxis allowDecimals={false} tick={tick} axisLine={false} tickLine={false} tickFormatter={(v) => num.format(v)} />
        <Tooltip
          cursor={{ fill: "rgba(42,120,214,0.08)" }}
          content={({ active, payload }: TipProps) =>
            active && payload?.length ? (
              <Box>
                <div>
                  {payload[0].payload.start.toFixed(1)}
                  {unit} to {payload[0].payload.end.toFixed(1)}
                  {unit}
                </div>
                <b>{num.format(payload[0].payload.count)}</b> {label.toLowerCase()}
              </Box>
            ) : null
          }
        />
        <Bar dataKey="count" fill={C.series} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Round axis ticks (0, 0.25, 0.5 ... or 0, 5k, 10k ...) so the last tick is a clean number just above the data. */
function niceTicks(min: number, max: number, target = 4): number[] {
  const span = Math.max(max - Math.min(min, 0), 0) || 1;
  const raw = span / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= raw - 1e-12) ?? 10) * mag;
  const lo = min < 0 ? Math.floor(min / step) * step : 0;
  const hi = Math.ceil(max / step - 1e-9) * step || step;
  const out: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) out.push(Math.round(v / step) * step);
  return out;
}

export interface MetricRow {
  label: string;
  value: number;
  highlight?: boolean;
  color?: string;
}

export function MetricBarChart({ rows, metric, height, format }: { rows: MetricRow[]; metric: string; height?: number; format?: (v: number) => string }) {
  const compact = useMediaQuery("(max-width: 991px)");
  if (!rows.length) return <div className="empty">Nothing to compare yet.</div>;
  const fmt = format ?? ((v: number) => v.toFixed(3));
  const h = height ?? Math.max(120, 34 * rows.length + 30);
  const max = Math.max(...rows.map((r) => r.value), 0);
  const min = Math.min(...rows.map((r) => r.value), 0);
  const ticks = niceTicks(min, max);
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 64, left: 8, bottom: 0 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke={C.grid} />
        <XAxis type="number" domain={[ticks[0], ticks[ticks.length - 1]]} ticks={ticks} tick={tick} axisLine={false} tickLine={false} tickFormatter={fmt} />
        <YAxis type="category" dataKey="label" width={compact ? 120 : 190} tick={tick} axisLine={false} tickLine={false} />
        <Tooltip
          cursor={{ fill: "rgba(42,120,214,0.08)" }}
          content={({ active, payload }: TipProps) =>
            active && payload?.length ? (
              <Box>
                <div>{payload[0].payload.label}</div>
                <b>{metric}</b>: {fmt(payload[0].value as number)}
              </Box>
            ) : null
          }
        />
        <Bar dataKey="value" radius={[0, 3, 3, 0]} isAnimationActive={false} label={{ position: "right", fill: C.text, fontSize: 12, formatter: (v: unknown) => fmt(Number(v)) }}>
          {rows.map((r) => (
            <Cell key={r.label} className={r.highlight && !r.color ? "bar-highlight" : undefined} fill={r.color ?? (r.highlight ? C.navy : C.series)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ImportanceChart({ items, top = 10 }: { items: ImportanceItem[]; top?: number }) {
  if (!items.length) return <div className="empty">No drivers recorded.</div>;
  const rows = items.slice(0, top).map((i) => ({ label: featureLabel(i.feature), value: i.importance }));
  return <MetricBarChart rows={rows} metric="Share of what made flagged days unusual" format={(v) => `${(v * 100).toFixed(1)}%`} />;
}

export function DetectionByTypeChart({ byType }: { byType: Record<string, number> }) {
  const rows = Object.entries(byType)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => ({ label: TYPE_LABEL[k] ?? k, value: v, color: TYPE_COLOR[k] }));
  return <MetricBarChart rows={rows} metric="Incidents caught" format={(v) => `${Math.round(v * 100)}%`} />;
}

export function PRCurveChart({ curves, height = 260 }: { curves: { name: string; points: PRPoint[]; color: string }[]; height?: number }) {
  const has = curves.some((c) => c.points.length);
  if (!has) return <div className="empty">No labels to draw a precision-recall curve.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart margin={{ top: 8, right: 16, left: 0, bottom: 14 }}>
        <CartesianGrid stroke={C.grid} />
        <XAxis type="number" dataKey="recall" domain={[0, 1]} tick={tick} axisLine={axisLine} tickLine={false} tickFormatter={(v) => `${Math.round(v * 100)}%`} label={{ value: "Share of real problems found", position: "insideBottom", offset: -8, fill: C.textMuted, fontSize: 12 }} />
        <YAxis type="number" domain={[0, 1]} tick={tick} axisLine={false} tickLine={false} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={60} label={{ value: "Alerts that are real", angle: -90, position: "insideLeft", fill: C.textMuted, fontSize: 12, style: { textAnchor: "middle" } }} />
        <Tooltip
          content={({ active, payload }: TipProps) =>
            active && payload?.length ? (
              <Box>
                {payload.map((p) => (
                  <div key={p.name}>
                    <b>{p.name}</b>: finds {Math.round(p.payload.recall * 100)}% of problems with {Math.round(p.payload.precision * 100)}% of alerts real
                  </div>
                ))}
              </Box>
            ) : null
          }
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        {curves.map((c) => (
          <Line key={c.name} data={[...c.points].sort((a, b) => a.recall - b.recall)} dataKey="precision" name={c.name} stroke={c.color} strokeWidth={2} dot={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function TrendChart({ rows, mode, types, height = 260 }: { rows: TrendRow[]; mode: "severity" | "type"; types: string[]; height?: number }) {
  if (!rows.length) return <div className="empty">No trend yet.</div>;
  const keys = mode === "severity" ? ["medium", "high", "critical"] : types.map((t) => `type:${t}`);
  const color = (k: string) => (mode === "severity" ? SEVERITY_COLOR[k] : TYPE_COLOR[k.slice(5)] ?? C.muted);
  const name = (k: string) => (mode === "severity" ? SEVERITY_LABEL[k] : TYPE_LABEL[k.slice(5)] ?? k.slice(5));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={rows} margin={{ top: 8, right: 12, left: -6, bottom: 0 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="date" tick={tick} axisLine={axisLine} tickLine={false} tickFormatter={shortDate} minTickGap={36} />
        <YAxis allowDecimals={false} tick={tick} axisLine={false} tickLine={false} tickFormatter={(v) => num.format(v)} />
        <Tooltip
          content={({ active, payload, label }: TipProps) =>
            active && payload?.length ? (
              <Box>
                <div style={{ marginBottom: 4 }}>
                  <b>{shortDate(String(label))}</b> · £{num.format(payload[0].payload.value_gbp)} at risk
                </div>
                {[...payload].reverse().map((p) => (
                  <div key={String(p.dataKey)}>
                    <span style={{ display: "inline-block", width: 10, height: 10, background: p.color, borderRadius: 2, marginRight: 6 }} />
                    {name(String(p.dataKey))}: <b>{num.format(p.value as number)}</b>
                  </div>
                ))}
              </Box>
            ) : null
          }
        />
        <Legend formatter={(v) => <span style={{ color: C.text, fontSize: 12 }}>{name(String(v))}</span>} />
        {keys.map((k) => (
          <Area key={k} type="monotone" dataKey={k} stackId="1" stroke={color(k)} fill={color(k)} fillOpacity={0.75} strokeWidth={1} isAnimationActive={false} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** The stock story of one SKU in one store: expected vs counted stock, the daily gap, flagged days and markers. */
export function SeriesChart({ points, height = 300, showTruth = false }: { points: SeriesPoint[]; height?: number; showTruth?: boolean }) {
  if (!points.length) return <div className="empty">No days to show.</div>;
  const data = points.map((p) => ({
    ...p,
    gap: p.variance_units,
    flag: p.severity > 0 ? Math.max(p.expected_closing, p.counted_closing) : null,
    lp: p.lp_flag ? 0 : null,
    truth: showTruth && p.truth_type ? 0 : null,
  }));
  // shade runs of flagged days
  const bands: { x1: string; x2: string; sev: number }[] = [];
  let open: { x1: string; x2: string; sev: number } | null = null;
  for (const p of points) {
    if (p.severity > 0) {
      if (open) {
        open.x2 = p.date;
        open.sev = Math.max(open.sev, p.severity);
      } else open = { x1: p.date, x2: p.date, sev: p.severity };
    } else if (open) {
      bands.push(open);
      open = null;
    }
  }
  if (open) bands.push(open);
  const sevName = ["", "medium", "high", "critical"];
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: -6, bottom: 0 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="date" tick={tick} axisLine={axisLine} tickLine={false} tickFormatter={shortDate} minTickGap={36} />
        <YAxis yAxisId="stock" tick={tick} axisLine={false} tickLine={false} />
        <YAxis yAxisId="gap" orientation="right" tick={tick} axisLine={false} tickLine={false} width={40} />
        {bands.map((b) => (
          <ReferenceArea key={b.x1} yAxisId="stock" x1={b.x1} x2={b.x2} fill={SEVERITY_COLOR[sevName[b.sev]]} fillOpacity={0.14} stroke={SEVERITY_COLOR[sevName[b.sev]]} strokeOpacity={0.5} ifOverflow="extendDomain" />
        ))}
        <ReferenceLine yAxisId="gap" y={0} stroke={C.grid} />
        <Tooltip
          content={({ active, payload }: TipProps) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as SeriesPoint;
            return (
              <Box>
                <div style={{ marginBottom: 4 }}>
                  <b>{shortDate(p.date)}</b>
                  {p.on_promo ? " · promotion" : ""}
                  {p.severity > 0 ? ` · flagged (${sevName[p.severity]})` : ""}
                </div>
                <div>
                  Expected {num.format(p.expected_closing)} · counted {num.format(p.counted_closing)} · gap <b>{num.format(p.variance_units)}</b>
                </div>
                <div>
                  Sold {p.sold_units} · received {p.received_units} · returned {p.returned_units}
                </div>
                <div>
                  Voids {p.void_count} · overrides {p.override_count} · keyed {p.manual_entry_scans} · after hours {p.after_hours_scans}
                </div>
                {p.percentile !== null ? <div>Unusualness: top {Math.max(0.01, (1 - p.percentile) * 100).toFixed(2)}% of days</div> : null}
                {p.lp_flag ? <div>Loss-prevention flag: {p.lp_flag}</div> : null}
                {showTruth && p.truth_type ? <div>Answer key: {TYPE_LABEL[p.truth_type] ?? p.truth_type}</div> : null}
              </Box>
            );
          }}
        />
        <Legend formatter={(v) => <span style={{ color: C.text, fontSize: 12 }}>{({ expected_closing: "Expected stock", counted_closing: "Counted stock", gap: "Daily gap (right axis)", lp: "Loss-prevention flag", truth: "Answer key" } as Record<string, string>)[String(v)] ?? String(v)}</span>} />
        <Bar yAxisId="gap" dataKey="gap" fill={C.muted} radius={[2, 2, 0, 0]} isAnimationActive={false} />
        <Line yAxisId="stock" type="stepAfter" dataKey="expected_closing" stroke={C.navy} strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line yAxisId="stock" type="stepAfter" dataKey="counted_closing" stroke={C.series} strokeWidth={2} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
        <Scatter yAxisId="gap" dataKey="lp" fill="#7a1fa2" shape="diamond" isAnimationActive={false} />
        {showTruth ? <Scatter yAxisId="gap" dataKey="truth" fill={C.critical} shape="cross" isAnimationActive={false} /> : null}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function HoursCurveChart({ curve, hours, height = 260 }: { curve: PlanCurvePoint[]; hours: number; height?: number }) {
  if (!curve.length) return <div className="empty">No curve yet.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={curve} margin={{ top: 8, right: 16, left: 4, bottom: 12 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="hours" type="number" domain={[0, "dataMax"]} tick={tick} axisLine={axisLine} tickLine={false} label={{ value: "Investigator hours", position: "insideBottom", offset: -6, fill: C.textMuted, fontSize: 12 }} />
        <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={(v) => gbp.format(v)} width={78} />
        <Tooltip
          content={({ active, payload }: TipProps) =>
            active && payload?.length ? (
              <Box>
                <div>
                  <b>{payload[0].payload.hours} hours</b> · {num.format(payload[0].payload.alerts)} alerts
                </div>
                <div>Expected recovery (ranked): <b>{gbp.format(payload[0].payload.expected_recovered)}</b></div>
                <div>Expected recovery (by £ at risk): {gbp.format(payload[0].payload.naive_expected)}</div>
                <div>Cost of the time: {gbp.format(payload[0].payload.cost)}</div>
              </Box>
            ) : null
          }
        />
        <Legend wrapperStyle={{ paddingTop: 16 }} formatter={(v) => <span style={{ color: C.text, fontSize: 12 }}>{({ expected_recovered: "Expected recovery, ranked by the model", naive_expected: "Working down by £ at risk", cost: "Cost of investigator time" } as Record<string, string>)[String(v)] ?? String(v)}</span>} />
        <Area type="monotone" dataKey="expected_recovered" stroke={C.series} fill={C.series} fillOpacity={0.18} strokeWidth={2} isAnimationActive={false} />
        <Line type="monotone" dataKey="naive_expected" stroke={C.navy} strokeDasharray="5 4" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="cost" stroke={C.muted} strokeWidth={2} dot={false} isAnimationActive={false} />
        <ReferenceLine x={hours} stroke={C.navy} strokeDasharray="4 4" label={{ value: "your hours", fill: C.navy, fontSize: 11, position: "insideTopRight" }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function PrecisionLineChart({ rows, height = 220 }: { rows: TriageGroup[]; height?: number }) {
  if (!rows.length) return <div className="empty">No reviews yet.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 12, left: -6, bottom: 0 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="key" tick={tick} axisLine={axisLine} tickLine={false} tickFormatter={shortDate} />
        <YAxis yAxisId="n" allowDecimals={false} tick={tick} axisLine={false} tickLine={false} />
        <YAxis yAxisId="p" orientation="right" domain={[0, 1]} tick={tick} axisLine={false} tickLine={false} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={44} />
        <Tooltip
          content={({ active, payload }: TipProps) =>
            active && payload?.length ? (
              <Box>
                <div>
                  <b>{shortDate(payload[0].payload.key)}</b>
                </div>
                <div>
                  {payload[0].payload.reviewed} reviewed, {payload[0].payload.true} real
                </div>
                <div>Precision {Math.round(payload[0].payload.precision * 100)}%</div>
              </Box>
            ) : null
          }
        />
        <Legend formatter={(v) => <span style={{ color: C.text, fontSize: 12 }}>{v === "reviewed" ? "Alerts reviewed" : "Share that were real"}</span>} />
        <Bar yAxisId="n" dataKey="reviewed" fill={C.muted} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Line yAxisId="p" type="monotone" dataKey="precision" stroke={C.good} strokeWidth={2} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
