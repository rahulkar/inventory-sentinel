"""Pydantic models for the Inventory Sentinel API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app import config

JobType = Literal["upload", "sync", "pipeline", "train", "detect", "retrain", "export"]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
Severity = Literal["medium", "high", "critical"]
Outcome = Literal["confirmed_theft", "counting_error", "process_issue", "false_alarm"]


# ---------------------------------------------------------------- jobs / config
class JobStep(BaseModel):
    key: str
    label: str
    status: JobStatus = "queued"
    seconds: float | None = None


class Job(BaseModel):
    job_id: str
    type: JobType
    title: str
    status: JobStatus = "queued"
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    percent: float = 0.0
    step: str | None = None
    message: str | None = None
    steps: list[JobStep] = []
    elapsed_seconds: float = 0.0
    eta_seconds: float | None = None
    estimate_seconds: float | None = None
    queue_position: int | None = None
    params: dict[str, Any] = {}
    detail: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    warnings: list[str] = []
    error: str | None = None


class AppConfig(BaseModel):
    max_rows: int
    max_upload_mb: int
    default_train_sample: int
    quick_train_sample: int
    default_alert_rate: float
    planner_defaults: dict[str, float]
    minutes_by_type: dict[str, int]
    persist_by_type: dict[str, float]
    triage_outcomes: list[str]
    anomaly_types: list[str]
    categories: list[str]
    timing: dict[str, float]


# ---------------------------------------------------------------- datasets
class ColumnInfo(BaseModel):
    name: str
    role: Literal["id", "date", "measure", "scan", "flag", "feature", "context", "ground_truth"]
    dtype: str
    label: str | None = None


class NumericStats(BaseModel):
    mean: float
    std: float
    min: float
    p50: float
    p95: float
    max: float


class HistBin(BaseModel):
    bin_start: float
    bin_end: float
    count: int


class DatasetStats(BaseModel):
    numeric: dict[str, NumericStats] = {}
    shrinkage_histogram: list[HistBin] = []
    rows_by_category: dict[str, int] = {}
    units_sold: int = 0
    net_variance_units: int = 0
    net_variance_value_gbp: float = 0.0


class Detection(BaseModel):
    """How an upload's columns were mapped onto the inventory schema."""

    column_map: dict[str, str] = {}
    missing_optional: list[str] = []
    dropped_features: list[str] = []
    source_file: str | None = None


class DatasetMeta(BaseModel):
    id: str
    name: str
    kind: Literal["synthetic", "upload", "connector"]  # "synthetic" only on datasets made before connectors existed
    created_at: str
    n_rows: int
    n_stores: int
    n_skus: int
    n_days: int
    n_series: int
    date_start: str
    date_end: str
    test_from_date: str
    has_truth: bool = False
    n_anomaly_rows: int = 0
    n_incidents: int = 0
    n_lp_flags: int = 0
    feature_columns: list[str] = []
    detect_features: list[str] = []
    categories: list[str] = []
    columns: list[ColumnInfo] = []
    stats: DatasetStats | None = None
    size_bytes: int = 0
    params: dict[str, Any] = {}
    detection: Detection | None = None
    warnings: list[str] = []


class PreviewResponse(BaseModel):
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int


class ExportStatus(BaseModel):
    dataset_id: str
    ready: bool
    size_bytes: int | None = None
    created_at: str | None = None
    job_id: str | None = None


class ConfigureRequest(BaseModel):
    column_map: dict[str, str] = {}
    name: str | None = None


# ---------------------------------------------------------------- models / training
class ParamSpec(BaseModel):
    name: str
    label: str
    type: Literal["int", "float", "select", "bool"]
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[Any] | None = None
    help: str | None = None


class ModelSpecOut(BaseModel):
    key: str
    label: str
    plain_label: str
    family: Literal["rules", "tree", "neural", "neighbours", "ensemble", "supervised"]
    description: str
    params: list[ParamSpec]
    recommended: bool
    available: bool
    reason: str | None = None
    engine: str
    onnx_ok: bool
    score_seconds_per_1m: float
    fit_seconds: float


class ModelSelection(BaseModel):
    key: str
    params: dict[str, Any] = {}


class TrainRequest(BaseModel):
    dataset_id: str
    models: list[ModelSelection]
    run_name: str | None = None
    train_sample_size: int = Field(config.DEFAULT_TRAIN_SAMPLE, ge=5_000, le=2_000_000)
    alert_rate: float = Field(config.DEFAULT_ALERT_RATE, ge=0.001, le=0.05)
    test_from_date: str | None = None
    exclude_lp_flagged: bool = True
    random_state: int = 42
    activate_best: bool = True  # scheduled retrains can train without swapping the model in use


class PRPoint(BaseModel):
    recall: float
    precision: float


class Metrics(BaseModel):
    label_source: Literal["ground_truth", "lp_flags", "none"] = "none"
    average_precision: float | None = None
    roc_auc: float | None = None
    precision_at_k: float | None = None
    k: int = config.PRECISION_AT_K
    recall_at_threshold: float | None = None
    precision_at_threshold: float | None = None
    incident_recall: float | None = None
    value_captured_pct: float | None = None
    alert_rate: float = 0.0
    detection_by_type: dict[str, float] = {}
    lp_recall: float | None = None  # share of loss-prevention-flagged days (held out of training) the model flags
    pr_curve: list[PRPoint] = []
    n_eval_rows: int = 0
    n_eval_positive: int = 0
    fit_seconds: float = 0.0
    score_seconds_per_1m: float = 0.0
    n_train: int = 0


class ImportanceItem(BaseModel):
    feature: str
    importance: float


class Thresholds(BaseModel):
    alert: float
    high: float
    critical: float


class Calibration(BaseModel):
    source: Literal["triage", "ground_truth", "lp_flags", "prior"] = "prior"
    note: str = ""
    percentiles: list[float] = []  # bin edges in percentile space
    p_true: list[float] = []


class ModelResult(BaseModel):
    key: str
    label: str
    status: Literal["pending", "running", "done", "failed"] = "pending"
    model_id: str | None = None
    metrics: Metrics | None = None
    error: str | None = None
    seconds: float | None = None


class TrainJob(BaseModel):
    job_id: str
    status: JobStatus
    run_name: str
    dataset_id: str
    results: list[ModelResult]
    best_model_id: str | None = None
    created_at: str
    dataset_name: str = ""
    message: str | None = None
    error: str | None = None
    progress: dict[str, int] = {}
    train_sample_size: int | None = None


class ModelSummary(BaseModel):
    model_id: str
    name: str
    key: str
    label: str
    dataset_id: str
    dataset_name: str
    run_name: str
    created_at: str
    is_active: bool = False
    metrics: Metrics
    engine: str = "sklearn"
    job_id: str | None = None
    parent_model_id: str | None = None
    train_sample_size: int | None = None


class ModelMeta(ModelSummary):
    params: dict[str, Any] = {}
    feature_columns: list[str] = []
    input_features: list[str] = []
    categories: list[str] = []
    thresholds: Thresholds
    score_quantiles: list[float] = []
    quantile_levels: list[float] = []
    calibration: Calibration = Calibration()
    importances: list[ImportanceItem] = []
    feature_baseline: dict[str, Any] = {}
    alert_rate: float = config.DEFAULT_ALERT_RATE
    test_from_date: str | None = None
    onnx_ok: bool = False
    onnx_reason: str | None = None
    notes: list[str] = []
    feedback_eval: dict[str, Any] = {}


class Experiment(BaseModel):
    job_id: str
    run_name: str
    dataset_id: str
    dataset_name: str
    created_at: str
    status: str
    models: list[ModelSummary]
    best_model_id: str | None = None
    train_sample_size: int | None = None
    live: TrainJob | None = None


class OnnxStatus(BaseModel):
    model_id: str
    available: bool
    ready: bool
    reason: str | None = None
    size_bytes: int | None = None
    max_abs_diff: float | None = None
    spearman: float | None = None
    top1_overlap: float | None = None
    n_checked: int | None = None
    created_at: str | None = None
    job_id: str | None = None
    warnings: list[str] = []


# ---------------------------------------------------------------- detection runs / alerts
class DetectRequest(BaseModel):
    dataset_id: str
    model_id: str | None = None


class Alert(BaseModel):
    alert_id: str
    alert_key: str
    store_id: str
    store_name: str
    region: str
    warehouse_team: str
    sku_id: str
    sku_name: str
    category: str
    start_date: str
    end_date: str
    n_days: int
    peak_score: float
    peak_percentile: float
    severity: Severity
    units_at_risk: int
    value_at_risk_gbp: float
    likely_type: str
    type_confidence: float
    reasons: list[str] = []
    p_true: float
    status: str = "open"  # open | outcome from triage
    truth_type: str | None = None  # demo vendor answer key, only when requested


class RunKpis(BaseModel):
    rows_scored: int
    flagged_rows: int
    incidents: int
    value_at_risk_gbp: float
    pct_rows_flagged: float
    stores_affected: int
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}


class RunEvaluation(BaseModel):
    label_source: str
    window: str
    incident_recall: float | None = None
    alert_precision: float | None = None
    value_captured_pct: float | None = None
    type_accuracy: float | None = None


class DetectionRun(BaseModel):
    run_id: str
    dataset_id: str
    dataset_name: str
    model_id: str
    model_name: str
    model_label: str
    created_at: str
    thresholds: Thresholds
    kpis: RunKpis
    evaluation: RunEvaluation | None = None
    seconds: float | None = None
    warnings: list[str] = []


class DetectionRunSummary(BaseModel):
    run_id: str
    dataset_id: str
    dataset_name: str
    model_id: str
    model_label: str
    created_at: str
    incidents: int
    value_at_risk_gbp: float
    model_in_use: bool = False


class AlertPage(BaseModel):
    total: int
    alerts: list[Alert]


class SeriesPoint(BaseModel):
    date: str
    opening_stock: int
    received_units: int
    sold_units: int
    returned_units: int
    adjustment_units: int
    expected_closing: int
    counted_closing: int
    variance_units: int
    pos_scans: int
    manual_entry_scans: int
    void_count: int
    override_count: int
    after_hours_scans: int
    receiving_scans: int
    on_promo: int
    score: float | None = None
    percentile: float | None = None
    severity: int = 0
    lp_flag: str | None = None
    truth_type: str | None = None


class SeriesResponse(BaseModel):
    store_id: str
    store_name: str
    sku_id: str
    sku_name: str
    category: str
    unit_cost: float
    points: list[SeriesPoint]
    alerts: list[Alert] = []
    flagged_reasons: dict[str, list[str]] = {}
    triage: list[dict[str, Any]] = []


class SeriesMatch(BaseModel):
    store_id: str
    store_name: str
    sku_id: str
    sku_name: str
    category: str
    n_alerts: int = 0


# ---------------------------------------------------------------- planner
class PlanRequest(BaseModel):
    run_id: str
    hours: float = Field(config.PLANNER_DEFAULTS["hours"], gt=0, le=10_000)
    hourly_cost: float = Field(config.PLANNER_DEFAULTS["hourly_cost"], gt=0, le=500)
    recovery_rate: float = Field(config.PLANNER_DEFAULTS["recovery_rate"], gt=0, le=1)
    horizon_days: int = Field(int(config.PLANNER_DEFAULTS["horizon_days"]), ge=0, le=365)
    minutes_by_type: dict[str, float] | None = None
    persist_by_type: dict[str, float] | None = None
    severities: list[Severity] | None = None
    teams: list[str] | None = None
    regions: list[str] | None = None
    store_ids: list[str] | None = None
    categories: list[str] | None = None
    date_from: str | None = None  # alerts that started on or after this day (YYYY-MM-DD)
    date_to: str | None = None
    include_reviewed: bool = False


class PlanCurvePoint(BaseModel):
    hours: float
    alerts: int
    expected_recovered: float
    cost: float
    roi: float
    naive_expected: float


class PlanBreakdown(BaseModel):
    key: str
    alerts: int
    hours: float
    expected_recovered: float
    value_at_risk_gbp: float


class PlanRow(BaseModel):
    priority: int
    alert_id: str
    team: str
    store_id: str
    store_name: str
    sku_id: str
    sku_name: str
    category: str
    start_date: str
    likely_type: str
    severity: str
    p_true: float
    value_at_risk_gbp: float
    expected_value_gbp: float
    minutes: float


class InvestigationPlan(BaseModel):
    run_id: str
    model_name: str
    hours: float
    hourly_cost: float
    recovery_rate: float
    horizon_days: int
    n_candidates: int
    n_selected: int
    hours_used: float
    cost: float
    expected_recovered: float
    net_benefit: float
    roi: float
    breakeven_hours: float | None
    naive_expected: float
    calibration_source: str
    by_team: list[PlanBreakdown]
    by_type: list[PlanBreakdown]
    by_severity: list[PlanBreakdown]
    curve: list[PlanCurvePoint]
    top_rows: list[PlanRow]
    explanation: str


# ---------------------------------------------------------------- triage / feedback
class TriageDecision(BaseModel):
    run_id: str
    alert_id: str
    outcome: Outcome
    note: str | None = None


class TriageBulk(BaseModel):
    run_id: str
    alert_ids: list[str]
    outcome: Outcome
    note: str | None = None


class SimulateTriageRequest(BaseModel):
    run_id: str
    days: int = Field(5, ge=1, le=30)
    per_day: int = Field(25, ge=1, le=200)
    noise: float = Field(0.1, ge=0, le=0.5)


class TriageSummary(BaseModel):
    dataset_id: str
    run_id: str | None
    reviewed: int
    true_alerts: int
    false_alarms: int
    precision: float | None
    open_alerts: int
    simulated: int
    by_day: list[dict[str, Any]] = []
    by_type: list[dict[str, Any]] = []
    by_severity: list[dict[str, Any]] = []
    by_team: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    can_retrain: bool = False
    retrain_reason: str | None = None


class ExecutiveSummary(BaseModel):
    """Executive overview for one run, filtered by period, location and category."""

    period: dict[str, Any]  # {start, end, days}
    options: dict[str, Any]  # {regions, stores[{store_id, store_name}], categories}
    revenue_at_risk_gbp: float
    value_at_risk_gbp: float
    open_cases: int
    threshold_gbp: float
    loss_prevented_gbp: float
    closed_cases: int
    inventory_accuracy_pct: float | None
    accuracy_delta_pp: float | None
    sla_within_pct: float | None
    sla_target_pct: float
    sla_days: int
    overdue_cases: int
    patterns: list[dict[str, Any]]  # [{type, cases, revenue_gbp}] open cases by likely type, most first
    top_categories: list[dict[str, Any]]  # [{category, cases, revenue_gbp}] open cases by product category, top 5
    top_locations: list[dict[str, Any]]


class RetrainRequest(BaseModel):
    alpha: float = Field(0.4, ge=0.0, le=0.9)
    run_name: str | None = None


# ---------------------------------------------------------------- misc
class Health(BaseModel):
    status: str
    versions: dict[str, str | None]
    data_dir: str
    env_issues: list[str] = []
    engines: dict[str, str] = {}


class Overview(BaseModel):
    n_datasets: int
    n_models: int
    n_runs: int = 0
    active_model: ModelSummary | None = None
    best_model: ModelSummary | None = None
    latest_run: DetectionRun | None = None
    top_alerts: list[Alert] = []
    recent_jobs: list[Job] = []


# ---------------------------------------------------------------- vendor connectors (MCP)
class ConnectorSync(BaseModel):
    at: str | None = None
    status: Literal["ok", "failed", "running"] | None = None
    job_id: str | None = None
    dataset_id: str | None = None
    rows: int = 0
    days_pulled: int = 0
    synced_through: str | None = None
    error: str | None = None
    warnings: list[str] = []
    seconds: float | None = None


class Connector(BaseModel):
    id: str
    name: str
    transport: Literal["mcp"] = "mcp"
    url: str
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    token: str = ""  # masked in API responses
    window_days: int = Field(config.SYNC_WINDOW_DAYS, ge=28, le=730)
    resync_days: int = Field(config.SYNC_RESYNC_DAYS, ge=0, le=30)
    retention: int = Field(config.CONNECTOR_RETENTION, ge=1, le=20)
    use_answer_key: bool = True  # only a demo vendor offers one; used to score models, never as an input
    feedback_from_tasks: bool = True  # closed vendor tasks become team feedback (triage)
    enabled: bool = True
    created_at: str
    capabilities: dict[str, Any] | None = None
    tested_at: str | None = None
    last_sync: ConnectorSync | None = None


class ConnectorIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=8, max_length=500)
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    token: str | None = None  # a masked value keeps the stored token
    window_days: int = Field(config.SYNC_WINDOW_DAYS, ge=28, le=730)
    resync_days: int = Field(config.SYNC_RESYNC_DAYS, ge=0, le=30)
    retention: int = Field(config.CONNECTOR_RETENTION, ge=1, le=20)
    use_answer_key: bool = True
    feedback_from_tasks: bool = True
    enabled: bool = True


class ConnectorTest(BaseModel):
    ok: bool
    capabilities: dict[str, Any] | None = None
    error: str | None = None
    seconds: float = 0.0


# ---------------------------------------------------------------- vendor tasks (write-back)
class VendorTaskDraft(BaseModel):
    run_id: str
    alert_id: str
    type: str
    priority: str | None = None
    title: str | None = None
    description: str | None = None
    sop_id: str | None = None
    sop_step: str | None = None
    note: str | None = None


class VendorTaskRequest(BaseModel):
    connector_id: str | None = None
    tasks: list[VendorTaskDraft] = Field(min_length=1, max_length=50)


class VendorTask(BaseModel):
    task_id: str
    connector_id: str
    alert_key: str | None = None
    alert_id: str | None = None
    run_id: str | None = None
    store_id: str
    sku_id: str | None = None
    type: str
    priority: str
    title: str
    status: str = "open"
    outcome: str | None = None
    outcome_units: int | None = None
    outcome_note: str | None = None
    sop_id: str | None = None
    sop_step: str | None = None
    source: str = "ui"
    created_at: str
    updated_at: str
    feedback_recorded: bool = False
    alert: dict[str, Any] = {}  # alert fields kept for feedback (dates, likely type, severity, team)


# ---------------------------------------------------------------- SOPs
class SopStep(BaseModel):
    id: str
    text: str
    role: str | None = None
    due_hours: float | None = None
    evidence: list[str] = []
    vendor_task: dict[str, Any] | None = None
    raised: list[VendorTask] = []


class SopEscalation(BaseModel):
    level: str
    label: str
    response_hours: float | None = None
    notify: list[str] = []


class SopSummary(BaseModel):
    id: str
    title: str
    version: str = "1"
    applies_to: list[str] = []
    parent: str | None = None
    owner_role: str | None = None
    summary: str | None = None


class Sop(SopSummary):
    escalation: list[dict[str, Any]] = []
    steps: list[SopStep] = []
    closure: list[str] = []
    triage_mapping: dict[str, str] = {}
    body: str = ""


class AlertSop(BaseModel):
    alert: Alert
    sop: Sop
    parent: SopSummary | None = None
    escalation: SopEscalation | None = None
    steps: list[SopStep] = []
    connector_id: str | None = None
    can_raise_tasks: bool = False
    task_types: list[str] = []


# ---------------------------------------------------------------- schedules
class ScheduleFrequency(BaseModel):
    kind: Literal["interval", "daily", "weekly"] = "daily"
    every_hours: int = Field(24, ge=1, le=168)
    at: str = "06:00"  # HH:MM in the schedule's timezone
    days: list[int] = [0, 1, 2, 3, 4, 5, 6]  # 0 = Monday


class ScheduleTrain(BaseModel):
    models: list[ModelSelection] = [ModelSelection(key="iforest")]
    train_sample_size: int = Field(config.QUICK_TRAIN_SAMPLE, ge=5_000, le=2_000_000)
    alert_rate: float = Field(config.DEFAULT_ALERT_RATE, ge=0.001, le=0.05)
    activate_retrained: bool = False
    min_interval_days: int = Field(0, ge=0, le=90)  # 0 = retrain on every run


class ScheduleAutoTasks(BaseModel):
    enabled: bool = False
    severities: list[Severity] = ["critical"]
    min_value_gbp: float = Field(0.0, ge=0)
    max_tasks: int = Field(10, ge=1, le=50)


class SchedulePipeline(BaseModel):
    sync: bool = True
    model_policy: Literal["active", "fixed", "retrain"] = "active"
    model_id: str | None = None
    train: ScheduleTrain = ScheduleTrain()
    auto_tasks: ScheduleAutoTasks = ScheduleAutoTasks()


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    connector_id: str
    timezone: str = "Europe/London"
    frequency: ScheduleFrequency = ScheduleFrequency()
    pipeline: SchedulePipeline = SchedulePipeline()
    catch_up: Literal["once", "skip"] = "once"


class Schedule(ScheduleIn):
    id: str
    created_at: str
    updated_at: str
    next_run_at: str | None = None  # UTC ISO
    last_run: dict[str, Any] | None = None
    last_retrain_at: str | None = None
    last_model_id: str | None = None  # the model this schedule last trained (retrain policy)


class ScheduleRun(BaseModel):
    run_id: str
    schedule_id: str
    data_through: str | None = None
    schedule_name: str
    trigger: Literal["timer", "manual", "catch_up"]
    status: Literal["queued", "running", "done", "failed", "skipped", "cancelled"]
    started_at: str
    finished_at: str | None = None
    job_id: str | None = None
    dataset_id: str | None = None
    model_id: str | None = None
    detection_run_id: str | None = None
    retrained: bool = False
    alerts: int | None = None
    new_alerts: int | None = None
    new_critical: int | None = None
    value_at_risk_gbp: float | None = None
    proposal_id: str | None = None
    error: str | None = None
    error_kind: str | None = None
    sop_id: str | None = None
    warnings: list[str] = []


class SchedulerStatus(BaseModel):
    running: bool
    last_tick: str | None = None
    tick_seconds: int
    schedules: int
    enabled: int
