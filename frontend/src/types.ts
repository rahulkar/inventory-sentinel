// ---------------------------------------------------------------- jobs / config
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type JobType = "upload" | "sync" | "pipeline" | "train" | "detect" | "retrain" | "export";
export type Severity = "medium" | "high" | "critical";
export type Outcome = "confirmed_theft" | "counting_error" | "process_issue" | "false_alarm";

export interface JobStep {
  key: string;
  label: string;
  status: JobStatus;
  seconds: number | null;
}

export interface Job {
  job_id: string;
  type: JobType;
  title: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  percent: number;
  step: string | null;
  message: string | null;
  steps: JobStep[];
  elapsed_seconds: number;
  eta_seconds: number | null;
  estimate_seconds: number | null;
  queue_position: number | null;
  params: Record<string, unknown>;
  detail: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  warnings: string[];
  error: string | null;
}

export interface AppConfig {
  max_rows: number;
  max_upload_mb: number;
  default_train_sample: number;
  quick_train_sample: number;
  default_alert_rate: number;
  planner_defaults: { hours: number; hourly_cost: number; recovery_rate: number; horizon_days: number };
  minutes_by_type: Record<string, number>;
  persist_by_type: Record<string, number>;
  triage_outcomes: Outcome[];
  anomaly_types: string[];
  categories: string[];
  timing: Record<string, number>;
}

// ---------------------------------------------------------------- datasets
export interface ColumnInfo {
  name: string;
  role: "id" | "date" | "measure" | "scan" | "flag" | "feature" | "context" | "ground_truth";
  dtype: string;
  label: string | null;
}

export interface NumericStats {
  mean: number;
  std: number;
  min: number;
  p50: number;
  p95: number;
  max: number;
}

export interface HistBin {
  bin_start: number;
  bin_end: number;
  count: number;
}

export interface DatasetStats {
  numeric: Record<string, NumericStats>;
  shrinkage_histogram: HistBin[];
  rows_by_category: Record<string, number>;
  units_sold: number;
  net_variance_units: number;
  net_variance_value_gbp: number;
}

export interface Detection {
  column_map: Record<string, string>;
  missing_optional: string[];
  dropped_features: string[];
  source_file: string | null;
}

export interface DatasetMeta {
  id: string;
  name: string;
  kind: "synthetic" | "upload" | "connector"; // "synthetic" only on datasets made before connectors existed
  created_at: string;
  n_rows: number;
  n_stores: number;
  n_skus: number;
  n_days: number;
  n_series: number;
  date_start: string;
  date_end: string;
  test_from_date: string;
  has_truth: boolean;
  n_anomaly_rows: number;
  n_incidents: number;
  n_lp_flags: number;
  feature_columns: string[];
  detect_features: string[];
  categories: string[];
  columns: ColumnInfo[];
  stats: DatasetStats | null;
  size_bytes: number;
  params: Record<string, unknown>;
  detection: Detection | null;
  warnings: string[];
}

export type PreviewTable = "daily" | "stores" | "skus" | "lp_flags" | "answer_key";

export interface PreviewResponse {
  table: string;
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
}

export interface ExportStatus {
  dataset_id: string;
  ready: boolean;
  size_bytes: number | null;
  created_at: string | null;
  job_id: string | null;
}

// ---------------------------------------------------------------- models
export interface ParamSpec {
  name: string;
  label: string;
  type: "int" | "float" | "select" | "bool";
  default: unknown;
  min: number | null;
  max: number | null;
  step: number | null;
  options: unknown[] | null;
  help: string | null;
}

export interface ModelSpec {
  key: string;
  label: string;
  plain_label: string;
  family: "rules" | "tree" | "neural" | "neighbours" | "ensemble" | "supervised";
  description: string;
  params: ParamSpec[];
  recommended: boolean;
  available: boolean;
  reason: string | null;
  engine: string;
  onnx_ok: boolean;
  score_seconds_per_1m: number;
  fit_seconds: number;
}

export interface ModelSelection {
  key: string;
  params: Record<string, unknown>;
}

export interface TrainRequest {
  dataset_id: string;
  models: ModelSelection[];
  run_name?: string | null;
  train_sample_size: number;
  alert_rate: number;
  test_from_date?: string | null;
  exclude_lp_flagged: boolean;
  random_state: number;
}

export interface PRPoint {
  recall: number;
  precision: number;
}

export interface Metrics {
  label_source: "ground_truth" | "lp_flags" | "none";
  average_precision: number | null;
  roc_auc: number | null;
  precision_at_k: number | null;
  k: number;
  recall_at_threshold: number | null;
  precision_at_threshold: number | null;
  incident_recall: number | null;
  value_captured_pct: number | null;
  alert_rate: number;
  detection_by_type: Record<string, number>;
  lp_recall: number | null;
  pr_curve: PRPoint[];
  n_eval_rows: number;
  n_eval_positive: number;
  fit_seconds: number;
  score_seconds_per_1m: number;
  n_train: number;
}

export interface ImportanceItem {
  feature: string;
  importance: number;
}

export interface Thresholds {
  alert: number;
  high: number;
  critical: number;
}

export interface Calibration {
  source: "triage" | "ground_truth" | "lp_flags" | "prior";
  note: string;
  percentiles: number[];
  p_true: number[];
}

export interface ModelResult {
  key: string;
  label: string;
  status: "pending" | "running" | "done" | "failed";
  model_id: string | null;
  metrics: Metrics | null;
  error: string | null;
  seconds: number | null;
}

export interface TrainJob {
  job_id: string;
  status: JobStatus;
  run_name: string;
  dataset_id: string;
  dataset_name: string;
  results: ModelResult[];
  best_model_id: string | null;
  created_at: string;
  message: string | null;
  error: string | null;
  progress: Record<string, number>;
  train_sample_size: number | null;
}

export interface ModelSummary {
  model_id: string;
  name: string;
  key: string;
  label: string;
  dataset_id: string;
  dataset_name: string;
  run_name: string;
  created_at: string;
  is_active: boolean;
  metrics: Metrics;
  engine: string;
  job_id: string | null;
  parent_model_id: string | null;
  train_sample_size: number | null;
}

export interface FeedbackEval {
  window: string;
  label_source: string;
  base: Record<string, number | null>;
  reranker: Record<string, number | null>;
  n_labels: Record<string, number>;
  classifier: string;
  alpha: number;
}

export interface ModelMeta extends ModelSummary {
  params: Record<string, unknown>;
  feature_columns: string[];
  input_features: string[];
  categories: string[];
  thresholds: Thresholds;
  score_quantiles: number[];
  quantile_levels: number[];
  calibration: Calibration;
  importances: ImportanceItem[];
  alert_rate: number;
  test_from_date: string | null;
  onnx_ok: boolean;
  onnx_reason: string | null;
  notes: string[];
  feedback_eval: Partial<FeedbackEval>;
}

export interface Experiment {
  job_id: string;
  run_name: string;
  dataset_id: string;
  dataset_name: string;
  created_at: string;
  status: string;
  models: ModelSummary[];
  best_model_id: string | null;
  train_sample_size: number | null;
  live: TrainJob | null;
}

export interface OnnxStatus {
  model_id: string;
  available: boolean;
  ready: boolean;
  reason: string | null;
  size_bytes: number | null;
  max_abs_diff: number | null;
  spearman: number | null;
  top1_overlap: number | null;
  n_checked: number | null;
  created_at: string | null;
  job_id: string | null;
  warnings: string[];
}

// ---------------------------------------------------------------- detection runs / alerts
export interface Alert {
  alert_id: string;
  alert_key: string;
  store_id: string;
  store_name: string;
  region: string;
  warehouse_team: string;
  sku_id: string;
  sku_name: string;
  category: string;
  start_date: string;
  end_date: string;
  n_days: number;
  peak_score: number;
  peak_percentile: number;
  severity: Severity;
  units_at_risk: number;
  value_at_risk_gbp: number;
  likely_type: string;
  type_confidence: number;
  reasons: string[];
  p_true: number;
  status: string;
  truth_type: string | null;
}

export interface RunKpis {
  rows_scored: number;
  flagged_rows: number;
  incidents: number;
  value_at_risk_gbp: number;
  pct_rows_flagged: number;
  stores_affected: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
}

export interface RunEvaluation {
  label_source: string;
  window: string;
  incident_recall: number | null;
  alert_precision: number | null;
  value_captured_pct: number | null;
  type_accuracy: number | null;
}

export interface DetectionRun {
  run_id: string;
  dataset_id: string;
  dataset_name: string;
  model_id: string;
  model_name: string;
  model_label: string;
  created_at: string;
  thresholds: Thresholds;
  kpis: RunKpis;
  evaluation: RunEvaluation | null;
  seconds: number | null;
  warnings: string[];
}

export interface DetectionRunSummary {
  run_id: string;
  dataset_id: string;
  dataset_name: string;
  model_id: string;
  model_label: string;
  created_at: string;
  incidents: number;
  value_at_risk_gbp: number;
  model_in_use: boolean;
}

export interface AlertPage {
  total: number;
  alerts: Alert[];
}

export interface TopRow {
  key: string;
  label: string;
  alerts: number;
  value_gbp: number;
  critical: number;
}

export interface TrendRow {
  date: string;
  value_gbp: number;
  critical: number;
  high: number;
  medium: number;
  [k: string]: string | number;
}

export interface HeatCell {
  store_id: string;
  store_name: string;
  category: string;
  alerts: number;
  value_gbp: number;
}

export interface Dashboard {
  run: DetectionRun;
  trend: TrendRow[];
  types: string[];
  heatmap: HeatCell[];
  categories: string[];
  stores: { store_id: string; store_name: string }[];
  by_region: TopRow[];
  top_stores: TopRow[];
  top_skus: TopRow[];
  top_teams: TopRow[];
  by_category: TopRow[];
}

export interface SeriesPoint {
  date: string;
  opening_stock: number;
  received_units: number;
  sold_units: number;
  returned_units: number;
  adjustment_units: number;
  expected_closing: number;
  counted_closing: number;
  variance_units: number;
  pos_scans: number;
  manual_entry_scans: number;
  void_count: number;
  override_count: number;
  after_hours_scans: number;
  receiving_scans: number;
  on_promo: number;
  score: number | null;
  percentile: number | null;
  severity: number;
  lp_flag: string | null;
  truth_type: string | null;
}

export interface TriageRecord {
  alert_key: string;
  run_id: string;
  alert_id: string;
  store_id: string;
  sku_id: string;
  start_date: string;
  end_date: string;
  likely_type: string;
  severity: string;
  warehouse_team: string;
  outcome: Outcome;
  note: string | null;
  source: "user" | "simulated" | "vendor_task";
  decided_at: string;
}

export interface SeriesResponse {
  store_id: string;
  store_name: string;
  sku_id: string;
  sku_name: string;
  category: string;
  unit_cost: number;
  points: SeriesPoint[];
  alerts: Alert[];
  flagged_reasons: Record<string, string[]>;
  triage: TriageRecord[];
}

export interface SeriesMatch {
  store_id: string;
  store_name: string;
  sku_id: string;
  sku_name: string;
  category: string;
  n_alerts: number;
}

// ---------------------------------------------------------------- planner
export interface PlanRequest {
  run_id: string;
  hours: number;
  hourly_cost: number;
  recovery_rate: number;
  horizon_days: number;
  severities?: Severity[] | null;
  teams?: string[] | null;
  include_reviewed?: boolean;
}

export interface PlanCurvePoint {
  hours: number;
  alerts: number;
  expected_recovered: number;
  cost: number;
  roi: number;
  naive_expected: number;
}

export interface PlanBreakdown {
  key: string;
  alerts: number;
  hours: number;
  expected_recovered: number;
  value_at_risk_gbp: number;
}

export interface PlanRow {
  priority: number;
  alert_id: string;
  team: string;
  store_id: string;
  store_name: string;
  sku_id: string;
  sku_name: string;
  category: string;
  start_date: string;
  likely_type: string;
  severity: Severity;
  p_true: number;
  value_at_risk_gbp: number;
  expected_value_gbp: number;
  minutes: number;
}

export interface InvestigationPlan {
  run_id: string;
  model_name: string;
  hours: number;
  hourly_cost: number;
  recovery_rate: number;
  horizon_days: number;
  n_candidates: number;
  n_selected: number;
  hours_used: number;
  cost: number;
  expected_recovered: number;
  net_benefit: number;
  roi: number;
  breakeven_hours: number | null;
  naive_expected: number;
  calibration_source: string;
  by_team: PlanBreakdown[];
  by_type: PlanBreakdown[];
  by_severity: PlanBreakdown[];
  curve: PlanCurvePoint[];
  top_rows: PlanRow[];
  explanation: string;
}

// ---------------------------------------------------------------- triage
export interface TriageGroup {
  key: string;
  reviewed: number;
  true: number;
  precision: number;
}

export interface TriageSummary {
  dataset_id: string;
  run_id: string | null;
  reviewed: number;
  true_alerts: number;
  false_alarms: number;
  precision: number | null;
  open_alerts: number;
  simulated: number;
  by_day: TriageGroup[];
  by_type: TriageGroup[];
  by_severity: TriageGroup[];
  by_team: TriageGroup[];
  matrix: { likely_type: string; outcome: Outcome; count: number }[];
  can_retrain: boolean;
  retrain_reason: string | null;
}

export interface Overview {
  n_datasets: number;
  n_models: number;
  n_runs: number;
  active_model: ModelSummary | null;
  best_model: ModelSummary | null;
  latest_run: DetectionRun | null;
  top_alerts: Alert[];
  recent_jobs: Job[];
}

// ---------------------------------------------------------------- assistant
export interface LlmSettingsOut {
  base_url: string;
  model: string;
  temperature: number;
  timeout_s: number;
  streaming: boolean;
  agent_mode: "team" | "single";
  embedding_model: string;
  price_input_per_m: number;
  price_output_per_m: number;
  monthly_budget_usd: number;
  verify_ssl: boolean;
  ca_bundle: string;
  tls_from_env: string | null;
  updated_at: string | null;
  api_key_masked: string;
  has_key: boolean;
  configured: boolean;
}

export interface LlmTestResult {
  ok: boolean;
  models: string[];
  chat_ok: boolean;
  reply: string | null;
  latency_ms: number | null;
  error: string | null;
}

export interface AssistantStatus {
  available: boolean;
  reason: string | null;
  configured: boolean;
  model: string;
  base_host: string;
  agent_mode: string;
  streaming: boolean;
  engine_ready: boolean;
  last_error: string | null;
  versions: Record<string, string | null>;
}

export interface UiState {
  page: string;
  mode?: string;
  tab?: string | null;
  selected_dataset_id: string | null;
  selected_run_id: string | null;
  selected_alert_id: string | null;
  drill_store_id: string | null;
  drill_sku_id: string | null;
  active_model_id: string | null;
  selected_schedule_id?: string | null;
}

export interface ChatRequest {
  session_id: string | null;
  message: string;
  ui: UiState;
}

export interface Proposal {
  proposal_id: string;
  session_id: string;
  kind: string;
  title: string;
  summary: string;
  params: Record<string, unknown>;
  estimate_seconds: number | null;
  warnings: string[];
  status: "pending" | "confirmed" | "cancelled" | "expired" | "failed";
  job_id: string | null;
  created_at: string;
  decided_at: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  ttl_s?: number | null;
  source?: "chat" | "scheduler" | "mcp";
}

export type ChatEvent =
  | { event: "session"; data: { session_id: string; title: string | null } }
  | { event: "text"; data: { delta: string; author: string } }
  | { event: "message_end"; data: { author: string } }
  | { event: "tool_call"; data: { id: string | null; name: string; args: Record<string, unknown>; label: string; author: string } }
  | { event: "tool_result"; data: { id: string | null; name: string; ok: boolean; summary: string; author: string } }
  | { event: "proposal"; data: Proposal }
  | { event: "transfer"; data: { to: string; from: string } }
  | { event: "usage"; data: { agent: string; prompt_tokens: number; completion_tokens: number; thoughts_tokens: number; cost_usd: number | null; session: SessionUsage } }
  | { event: "error"; data: { code: string; message: string } }
  | { event: "done"; data: { session_id: string; elapsed_ms: number } };

export interface ToolActivity {
  id: string | null;
  name: string;
  label: string;
  ok: boolean | null;
  summary: string | null;
  author?: string | null; // agent that made the call
  to?: string | null; // hand-over target (name === "transfer")
  at?: number; // client timestamps (ms) for the thinking trail
  doneAt?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  author?: string | null;
  text: string;
  tools: ToolActivity[];
  proposals: Proposal[];
  timestamp?: number | null;
  pending?: boolean;
  error?: string | null;
  usage?: { llm_calls: number; prompt_tokens: number; completion_tokens: number; cost_usd: number; unpriced: boolean };
  startedAt?: number;
  endedAt?: number;
}

export interface SessionSummary {
  session_id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  n_messages: number;
}

export interface Health {
  status: string;
  versions: Record<string, string | null>;
  data_dir: string;
  env_issues: string[];
  engines: Record<string, string>;
}

export interface SessionUsage {
  llm_calls: number;
  tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  unpriced_calls: number;
}

export interface AgentUsage {
  name: string;
  label: string;
  description: string;
  tools: string[];
  n_tools: number;
  in_team: boolean;
  llm_calls: number;
  tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  thoughts_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  cost_usd: number;
  unpriced_calls: number;
  invocations: number;
  share_of_cost: number;
}

export interface UsageReport {
  since: string | null;
  session_id: string | null;
  model: string;
  pricing: { model: string; input_per_m: number; output_per_m: number; source: string; known: boolean; currency: string };
  totals: SessionUsage & { thoughts_tokens: number; cached_tokens: number; invocations: number; sessions: number; agents: number };
  agents: AgentUsage[];
  tools: { name: string; calls: number }[];
  by_day: { day: string; llm_calls: number; tool_calls: number; total_tokens: number; cost_usd: number; invocations: number }[];
  sessions: { session_id: string; last_ts: number; llm_calls: number; tool_calls: number; total_tokens: number; cost_usd: number; invocations: number }[];
}

export interface FinOpsSpend {
  cost_usd: number;
  tokens: number;
  calls: number;
  unpriced_calls: number;
}

export interface FinOpsReport {
  since: string | null;
  currency: string;
  periods: { today: FinOpsSpend; last_7_days: FinOpsSpend; month_to_date: FinOpsSpend; all_time: FinOpsSpend };
  budget: { monthly_usd: number; month: string; spent_usd: number; projected_usd: number | null; used_pct: number | null; status: "none" | "ok" | "at_risk" | "over" };
  chat: {
    conversations: number;
    questions: number;
    llm_calls: number;
    tool_calls: number;
    tokens: number;
    cost_usd: number;
    unpriced_calls: number;
    avg_cost_per_question: number;
    avg_tokens_per_question: number;
    avg_calls_per_question: number;
  };
  agents: (FinOpsSpend & { name: string; label: string; invocations: number })[];
  embeddings: { model: string; calls: number; inputs: number; tokens: number; cost_usd: number; unpriced_calls: number; estimated_tokens: boolean };
  daily: { day: string; chat_usd: number; embeddings_usd: number; tokens: number }[];
  pricing: {
    chat: { model: string; input_per_m: number; output_per_m: number; source: string; known: boolean } | null;
    embeddings: { model: string; input_per_m: number; source: string; known: boolean } | null;
  };
}

// ---------------------------------------------------------------- vendor connectors (MCP)
export interface ConnectorSync {
  at: string | null;
  status: "ok" | "failed" | "running" | null;
  job_id: string | null;
  dataset_id: string | null;
  rows: number;
  days_pulled: number;
  synced_through: string | null;
  error: string | null;
  warnings: string[];
  seconds: number | null;
}

export interface ConnectorCapabilities {
  contract: string;
  version: string;
  vendor: { name: string; system?: string };
  status: string;
  timezone?: string;
  currency?: string;
  data_range?: { first_date: string; last_date: string | null };
  business_date?: string;
  counts?: { stores: number; skus: number };
  fields?: { daily: string[] };
  features?: { lp_flags?: boolean; tasks?: boolean; live_lookup?: boolean; answer_key?: boolean; answer_key_demo_only?: boolean };
  task_types?: string[];
  backoffice_url?: string;
  seeding?: { progress: number; message: string | null };
}

export interface Connector {
  id: string;
  name: string;
  transport: "mcp";
  url: string;
  auth_header: string;
  auth_scheme: string;
  token: string; // masked
  window_days: number;
  resync_days: number;
  retention: number;
  use_answer_key: boolean;
  feedback_from_tasks: boolean;
  enabled: boolean;
  created_at: string;
  capabilities: ConnectorCapabilities | null;
  tested_at: string | null;
  last_sync: ConnectorSync | null;
}

export interface ConnectorIn {
  name: string;
  url: string;
  auth_header?: string;
  auth_scheme?: string;
  token?: string | null;
  window_days?: number;
  resync_days?: number;
  retention?: number;
  use_answer_key?: boolean;
  feedback_from_tasks?: boolean;
  enabled?: boolean;
}

export interface ConnectorTest {
  ok: boolean;
  capabilities: ConnectorCapabilities | null;
  error: string | null;
  seconds: number;
}

export interface StockPosition {
  store: { store_id: string; store_name: string; region: string };
  sku: { sku_id: string; sku_name: string; category: string; unit_cost: number };
  as_of: string;
  on_hand: number | null;
  last_days: { date: string; opening: number; received: number; sold: number; returned: number; adjusted: number; expected_closing: number; counted_closing: number; variance: number }[];
}

// ---------------------------------------------------------------- vendor tasks
export interface VendorTask {
  task_id: string;
  connector_id: string;
  alert_key: string | null;
  alert_id: string | null;
  run_id: string | null;
  store_id: string;
  sku_id: string | null;
  type: string;
  priority: string;
  title: string;
  status: string;
  outcome: string | null;
  outcome_units: number | null;
  outcome_note: string | null;
  sop_id: string | null;
  sop_step: string | null;
  source: string;
  created_at: string;
  updated_at: string;
  feedback_recorded: boolean;
}

export interface VendorTaskDraft {
  run_id: string;
  alert_id: string;
  type: string;
  priority?: string | null;
  title?: string | null;
  sop_id?: string | null;
  sop_step?: string | null;
  note?: string | null;
}

export interface VendorTaskResult {
  created: VendorTask[];
  existing: VendorTask[];
  failed: { alert_id: string; type: string | null; error: string }[];
}

// ---------------------------------------------------------------- SOPs
export interface SopStep {
  id: string;
  text: string;
  role: string | null;
  due_hours: number | null;
  evidence: string[];
  vendor_task: { type: string; priority?: string; title?: string; description?: string } | null;
  raised: VendorTask[];
}

export interface SopEscalation {
  level: string;
  label: string;
  response_hours: number | null;
  notify: string[];
}

export interface SopSummary {
  id: string;
  title: string;
  version: string;
  applies_to: string[];
  parent: string | null;
  owner_role: string | null;
  summary: string | null;
}

export interface Sop extends SopSummary {
  escalation: Record<string, unknown>[];
  steps: SopStep[];
  closure: string[];
  triage_mapping: Record<string, string>;
  body: string;
}

export interface AlertSop {
  alert: Alert;
  sop: Sop;
  parent: SopSummary | null;
  escalation: SopEscalation | null;
  steps: SopStep[];
  connector_id: string | null;
  can_raise_tasks: boolean;
  task_types: string[];
}

// ---------------------------------------------------------------- schedules
export interface ScheduleFrequency {
  kind: "interval" | "daily" | "weekly";
  every_hours: number;
  at: string;
  days: number[];
}

export interface SchedulePipeline {
  sync: boolean;
  model_policy: "active" | "fixed" | "retrain";
  model_id: string | null;
  train: { models: { key: string; params: Record<string, unknown> }[]; train_sample_size: number; alert_rate: number; activate_retrained: boolean; min_interval_days: number };
  auto_tasks: { enabled: boolean; severities: Severity[]; min_value_gbp: number; max_tasks: number };
}

export interface ScheduleIn {
  name: string;
  enabled: boolean;
  connector_id: string;
  timezone: string;
  frequency: ScheduleFrequency;
  pipeline: SchedulePipeline;
  catch_up: "once" | "skip";
}

export interface Schedule extends ScheduleIn {
  id: string;
  created_at: string;
  updated_at: string;
  next_run_at: string | null;
  last_run: Partial<ScheduleRun> | null;
  last_retrain_at: string | null;
  last_model_id: string | null;
}

export interface ScheduleRun {
  run_id: string;
  schedule_id: string;
  schedule_name: string;
  data_through: string | null;
  trigger: "timer" | "manual" | "catch_up";
  status: "queued" | "running" | "done" | "failed" | "skipped" | "cancelled";
  started_at: string;
  finished_at: string | null;
  job_id: string | null;
  dataset_id: string | null;
  model_id: string | null;
  detection_run_id: string | null;
  retrained: boolean;
  alerts: number | null;
  new_alerts: number | null;
  new_critical: number | null;
  value_at_risk_gbp: number | null;
  proposal_id: string | null;
  error: string | null;
  error_kind: string | null;
  sop_id: string | null;
  warnings: string[];
}

export interface SchedulerStatus {
  running: boolean;
  last_tick: string | null;
  tick_seconds: number;
  schedules: number;
  enabled: number;
}

export interface ExecutiveSummary {
  period: { start: string; end: string; days: number };
  options: { regions: string[]; stores: { store_id: string; store_name: string }[]; categories: string[] };
  revenue_at_risk_gbp: number;
  value_at_risk_gbp: number;
  open_cases: number;
  threshold_gbp: number;
  loss_prevented_gbp: number;
  closed_cases: number;
  inventory_accuracy_pct: number | null;
  accuracy_delta_pp: number | null;
  sla_within_pct: number | null;
  sla_target_pct: number;
  sla_days: number;
  overdue_cases: number;
  patterns: { type: string; cases: number; revenue_gbp: number }[];
  top_categories: { category: string; cases: number; revenue_gbp: number }[];
  top_locations: { store_id: string; label: string; value_gbp: number }[];
}

export interface LibraryDocument {
  id: string;
  name: string;
  kind: "sop" | "reference";
  ext: string;
  size_bytes: number;
  n_chunks: number;
  n_words: number;
  sop_id: string | null;
  created_at: string;
  note: string | null;
  duplicate?: boolean;
}

export interface DocumentLibrary {
  documents: LibraryDocument[];
  builtin: { name: string; kind: "guide" | "sop"; n_chunks: number }[];
  index: {
    passages: number;
    embedded: number;
    embedding_model: string | null;
    mode: "hybrid" | "keyword";
    running: boolean;
    done: number;
    total: number;
    error: string | null;
    finished_at: string | null;
  };
  limits: { max_mb: number; types: string[] };
}

export interface DocSearchHit {
  source: string;
  section: string;
  text: string;
  score: number;
  match: "keyword" | "meaning" | "both";
  doc_id?: string;
}
