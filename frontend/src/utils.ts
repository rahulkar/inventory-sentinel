import type { AppConfig } from "./types";

export const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
export const gbp2 = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 2 });
export const num = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

export function fmtNum(v: unknown, digits = 2): string {
  if (v === null || v === undefined || v === "") return "–";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return num.format(v);
    return v.toLocaleString("en-GB", { maximumFractionDigits: digits });
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

export function fmtPct(v: number, digits = 0): string {
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "–";
  const s = Math.max(0, Math.round(seconds));
  if (s < 10) return "a few seconds";
  if (s < 60) return `about ${Math.round(s / 5) * 5} seconds`;
  const m = Math.round(s / 60);
  if (m < 60) return `about ${m} minute${m === 1 ? "" : "s"}`;
  const h = Math.floor(m / 60);
  return `about ${h} h ${m - h * 60} min`;
}

export function fmtClock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "–";
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

export function fmtBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "–";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/// ---------------------------------------------------------------- plain-language dictionary
export interface FeatureInfo {
  label: string;
  help?: string;
  unit?: "days" | "gbp" | "count" | "share" | "pct" | "z";
}

export const FEATURE_LABELS: Record<string, FeatureInfo> = {
  date: { label: "Date" },
  store_id: { label: "Store" },
  sku_id: { label: "SKU" },
  opening_stock: { label: "Opening stock", unit: "count" },
  received_units: { label: "Units received", unit: "count" },
  sold_units: { label: "Units sold", unit: "count" },
  returned_units: { label: "Units returned", unit: "count" },
  transfer_in_units: { label: "Transferred in", unit: "count" },
  transfer_out_units: { label: "Transferred out", unit: "count" },
  adjustment_units: { label: "Recorded adjustment", unit: "count" },
  expected_closing: { label: "Expected closing stock", help: "What the books say should be on the shelf tonight.", unit: "count" },
  counted_closing: { label: "Counted closing stock", help: "What the evening count found.", unit: "count" },
  pos_scans: { label: "Till scans", unit: "count" },
  manual_entry_scans: { label: "Manually keyed scans", unit: "count" },
  void_count: { label: "Voided lines", unit: "count" },
  override_count: { label: "Price/quantity overrides", unit: "count" },
  after_hours_scans: { label: "After-hours scans", unit: "count" },
  receiving_scans: { label: "Units scanned at receiving", unit: "count" },
  on_promo: { label: "On promotion" },
  shrinkage_pct: { label: "Shrinkage % today", help: "(expected - counted) / expected.", unit: "pct" },
  variance_z_series: { label: "Stock gap vs this item's normal", help: "Today's gap in units of the item's usual count noise.", unit: "z" },
  shrink_sum_7_z: { label: "Stock missing over 7 days", help: "Count noise cancels out over a week; genuine loss keeps adding up.", unit: "z" },
  shrink_pct_7: { label: "Shrinkage % over 7 days", unit: "pct" },
  reversal_index: { label: "Gap that reverses yesterday's", help: "High when a miscount is corrected the next day.", unit: "z" },
  velocity_z: { label: "Sales vs normal", help: "Allows for promotions.", unit: "z" },
  zero_sales_streak: { label: "Missed sales in a no-sales run", help: "Expected sales lost while the item showed stock but did not sell." },
  receiving_gap_units: { label: "Delivery booked vs scanned" },
  received_vs_typical: { label: "Delivery size vs normal" },
  adjustment_vs_typical: { label: "Adjustment size vs normal" },
  returns_z: { label: "Returns vs normal", unit: "z" },
  manual_entry_z: { label: "Keyed-in scans vs store habit", unit: "z" },
  void_z: { label: "Voids vs store habit", unit: "z" },
  override_z: { label: "Overrides vs store habit", unit: "z" },
  after_hours_z: { label: "After-hours scans vs normal", unit: "z" },
  store_day_shrink_z: { label: "Store-wide shrink that day", help: "Several items missing in one store on one day.", unit: "z" },
  variance_units: { label: "Stock gap (units, log)" },
  variance_value: { label: "Stock gap (£, log)" },
  stock_cover_days: { label: "Days of stock on hand (log)" },
  is_delivery_day: { label: "Delivery day" },
  log_unit_cost: { label: "Unit cost (log)" },
  dow: { label: "Day of week" },
  category: { label: "Category" },
  truth_type: { label: "Answer key: anomaly type" },
  truth_incident: { label: "Answer key: incident" },
  truth_loss_units: { label: "Answer key: units lost" },
  flag_type: { label: "Flag type" },
  loss_value_gbp: { label: "Loss value", unit: "gbp" },
  unit_cost: { label: "Unit cost", unit: "gbp" },
  unit_price: { label: "Unit price", unit: "gbp" },
};

export function featureLabel(name: string): string {
  return FEATURE_LABELS[name]?.label ?? titleCase(name);
}

export function featureHelp(name: string): string | undefined {
  return FEATURE_LABELS[name]?.help;
}

export function fmtFeatureValue(name: string, v: unknown): string {
  const unit = FEATURE_LABELS[name]?.unit;
  if (typeof v === "number") {
    if (unit === "gbp") return gbp2.format(v);
    if (unit === "share") return fmtPct(v, 0);
    if (unit === "pct") return `${v.toFixed(1)}%`;
    if (unit === "count") return num.format(Math.round(v));
    return fmtNum(v);
  }
  if (name === "on_promo" || name === "is_delivery_day") return v === 1 || v === "1" || v === true ? "yes" : "no";
  return fmtNum(v);
}

export const MODEL_PLAIN: Record<string, string> = {
  zscore: "Rule of thumb: flags days whose shrinkage is far from normal for the category",
  iforest: "Isolation forest: unusual days are isolated by few random splits",
  autoencoder: "Autoencoder: a small network rebuilds normal days; what it cannot rebuild is unusual",
  lof: "Local outlier factor: days in a sparser neighbourhood than their neighbours",
  reranker: "Feedback re-ranker: a detector plus what investigators confirmed",
};

export const TYPE_LABEL: Record<string, string> = {
  theft_external: "External theft",
  theft_internal: "Internal theft",
  scan_fraud: "Till / scan fraud",
  counting_error: "Counting error",
  receiving_error: "Receiving error",
  data_entry_error: "Data-entry error",
  velocity_shift: "Sales pattern change",
  unclear: "Unclear",
  none: "Normal",
};

export const TYPE_HELP: Record<string, string> = {
  theft_external: "Stock going missing over several days without matching sales.",
  theft_internal: "Losses with after-hours activity or several items at once in one store.",
  scan_fraud: "Voids, overrides, keyed-in items or refunds well above the store's habit.",
  counting_error: "A gap one day that the next count reverses.",
  receiving_error: "A delivery booked in at a different quantity from what arrived.",
  data_entry_error: "A quantity typed ten times too large, or with the wrong sign.",
  velocity_shift: "Sales stop while stock shows (phantom stock) or jump with no promotion.",
  unclear: "Several small signals together.",
};

export const SEVERITY_LABEL: Record<string, string> = { critical: "Critical", high: "High", medium: "Medium" };
export const OUTCOME_LABEL: Record<string, string> = { confirmed_theft: "Confirmed theft", counting_error: "Counting error", process_issue: "Process issue", false_alarm: "False alarm", open: "Open" };
export const SOURCE_LABEL: Record<string, string> = { ground_truth: "synthetic answer key", lp_flags: "loss-prevention flags", triage: "your team's decisions", prior: "an assumption (no labels yet)", none: "no labels" };

export const plain = {
  ap: (v: number | null | undefined) => (v === null || v === undefined ? "not measured" : `average precision ${v.toFixed(2)}`),
  lift: (v: number | null | undefined, base: number | null | undefined) => (v && base ? `${(v / base).toFixed(1)}x the rule of thumb` : ""),
  recall: (v: number | null | undefined) => (v === null || v === undefined ? "–" : `catches ${Math.round(v * 100)}% of incidents`),
  pct: (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? "–" : `${(v * 100).toFixed(digits)}%`),
  ptrue: (v: number) => `${Math.round(v * 10)} in 10 alerts like this are real`,
};

// ---------------------------------------------------------------- estimates
export function estimateSeconds(kind: "generate" | "train" | "detect" | "export", opts: { rows?: number; modelKeys?: string[]; sample?: number; scorePer1m?: number }, timing: Record<string, number> | undefined): number {
  const t = timing ?? {};
  const rows = opts.rows ?? 0;
  switch (kind) {
    case "generate":
      return 3 + (t.generate_s_per_1m ?? 9) * (rows / 1e6);
    case "train":
      return 5 + (opts.modelKeys ?? []).reduce((acc, k) => acc + (t[`model_${k}_fit_s`] ?? 5) * ((opts.sample ?? 200_000) / 200_000) + (t[`model_${k}_score_s_per_1m`] ?? 10) * 0.5, 0);
    case "detect":
      return 5 + ((opts.scorePer1m ?? 20) + (t.detect_overhead_s_per_1m ?? 1.5)) * (rows / 1e6);
    case "export":
      return 3 + (t.export_s_per_1m ?? 18) * (rows / 1e6);
  }
}

export function defaultConfig(): AppConfig {
  return {
    min_rows: 1_000_000,
    max_rows: 10_000_000,
    default_stores: 80,
    default_skus: 500,
    default_days: 125,
    max_upload_mb: 2048,
    default_train_sample: 200_000,
    quick_train_sample: 100_000,
    default_alert_rate: 0.008,
    planner_defaults: { hours: 120, hourly_cost: 28, recovery_rate: 0.4, horizon_days: 28 },
    minutes_by_type: {},
    persist_by_type: {},
    triage_outcomes: ["confirmed_theft", "counting_error", "process_issue", "false_alarm"],
    anomaly_types: [],
    categories: [],
    timing: {},
  };
}

export function isTerminal(status: string): boolean {
  return status === "done" || status === "failed" || status === "cancelled";
}

/** Executive wording for P(true): a word instead of a percentage. */
export function confidenceWord(p: number): "High" | "Medium" | "Low" {
  return p >= 0.8 ? "High" : p >= 0.5 ? "Medium" : "Low";
}

/** £657k / £1.2m style money for headline numbers. */
export function compactGbp(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e6) return `£${(v / 1e6).toFixed(a >= 1e7 ? 0 : 1)}m`;
  if (a >= 1e3) return `£${Math.round(v / 1e3)}k`;
  return `£${Math.round(v)}`;
}
