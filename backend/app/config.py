"""Paths, limits and domain constants for the Inventory Sentinel backend."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("SENTINEL_DATA_DIR") or ROOT / "data")  # override for tests (e.g. data_smoke)
DATASETS_DIR = DATA_DIR / "datasets"
MODELS_DIR = DATA_DIR / "models"
RUNS_DIR = DATA_DIR / "runs"
TRIAGE_DIR = DATA_DIR / "triage"
EXPORTS_DIR = DATA_DIR / "exports"
REGISTRY_PATH = DATA_DIR / "registry.json"
FRONTEND_DIST = ROOT / "frontend" / "dist"
SOPS_DIR = ROOT / "docs" / "sops"

# ---- vendor connectors (MCP), syncs, schedules, vendor tasks
CONNECTORS_PATH = DATA_DIR / "connectors.json"
CONNECTORS_DIR = DATA_DIR / "connectors"  # per-connector mirror of the vendor's data (only new days are pulled)
SCHEDULES_PATH = DATA_DIR / "schedules.json"
SCHEDULE_RUNS_PATH = DATA_DIR / "schedule_runs.jsonl"
VENDOR_TASKS_PATH = DATA_DIR / "vendor_tasks.jsonl"
DEFAULT_CONNECTOR_URL = os.environ.get("SENTINEL_DEFAULT_CONNECTOR_URL") or None  # registered at startup when no connector exists
SYNC_PAGE_SIZE = 50_000
SYNC_WINDOW_DAYS = 120  # each snapshot holds the last N days
SYNC_RESYNC_DAYS = 3  # re-pull the last N days on every sync (late corrections)
CONNECTOR_RETENTION = 3  # snapshots kept per connector
MCP_CALL_TIMEOUT_S = 120
SCHEDULER_TICK_S = 30
SCHEDULER_PROPOSAL_TTL_S = 72 * 3600

# ---- scale / limits (rows = stores x SKUs x days)
MAX_UPLOAD_MB = 2048
MAX_ROWS = 10_000_000
GEN_BLOCK_STORES = 10  # features are engineered in blocks of this many stores
CSV_WRITE_CHUNK_ROWS = 500_000
CSV_READ_CHUNK_ROWS = 1_000_000
UPLOAD_SAMPLE_ROWS = 50_000
PREVIEW_ROWS_MAX = 200
SCORE_CHUNK_ROWS = 250_000

# ---- training / detection
DEFAULT_TRAIN_SAMPLE = 200_000
QUICK_TRAIN_SAMPLE = 100_000
DEFAULT_ALERT_RATE = 0.008  # share of training rows above the alert threshold
SEVERITY_QUANTILES = {"high": 0.998, "critical": 0.9995}
TEST_WINDOW_SHARE = 0.28  # last 28% of days are the evaluation window
EVAL_NEGATIVES = 300_000
PRECISION_AT_K = 1000
INCIDENT_GAP_DAYS = 1
RECOMMENDED_MODELS = ["zscore", "iforest", "autoencoder", "lof"]

# ---- investigation planner
PLANNER_DEFAULTS = {"hours": 120.0, "hourly_cost": 28.0, "recovery_rate": 0.4, "horizon_days": 28}
MINUTES_BY_TYPE = {
    "theft_external": 60, "theft_internal": 90, "scan_fraud": 75, "counting_error": 15,
    "receiving_error": 30, "data_entry_error": 10, "velocity_shift": 25, "unclear": 45,
}
PERSIST_BY_TYPE = {
    "theft_external": 0.6, "theft_internal": 0.8, "scan_fraud": 0.7, "counting_error": 0.1,
    "receiving_error": 0.1, "data_entry_error": 0.1, "velocity_shift": 0.5, "unclear": 0.3,
}
# share of the value at risk that is real money a team can recover or stop losing (book errors are corrected, not recovered)
CASH_SHARE_BY_TYPE = {
    "theft_external": 1.0, "theft_internal": 1.0, "scan_fraud": 1.0, "counting_error": 0.1,
    "receiving_error": 0.8, "data_entry_error": 0.05, "velocity_shift": 0.5, "unclear": 0.5,
}
PLANNER_CURVE_POINTS = 21
PLANNER_TOP_ROWS = 50

# ---- triage / feedback
TRIAGE_OUTCOMES = ["confirmed_theft", "counting_error", "process_issue", "false_alarm"]
RETRAIN_MIN_REVIEWED = 30
RETRAIN_MIN_EACH = 5

CACHE_COLUMNS = 4
CACHE_PIPELINES = 4
CACHE_RUNS = 3
JOBS_KEEP = 100
EXPORT_COMPRESSLEVEL = 1

# ---- assistant (Google ADK + LiteLLM gateway + MCP)
SETTINGS_PATH = DATA_DIR / "settings.json"
ASSISTANT_DB = DATA_DIR / "assistant.sqlite"
ASSISTANT_PROPOSALS_PATH = DATA_DIR / "assistant_proposals.json"
ASSISTANT_TOOL_ROW_CAP = 20
ASSISTANT_TEXT_CAP = 600
ASSISTANT_TIMEOUT_S = 120
ASSISTANT_PROPOSAL_TTL_S = 1800
ASSISTANT_MAX_LLM_CALLS = 24
ASSISTANT_USAGE_PATH = DATA_DIR / "assistant_usage.json"
ASSISTANT_USAGE_CAP = 20_000

# ---- timing rules of thumb (seconds), measured on a 6-core laptop; UI estimates only
TIMING = {
    "sync_s_per_1m": 25.0,  # first full pull over MCP on localhost, incl. features
    "upload_s_per_mb": 0.25,
    "export_s_per_1m": 4.5,  # measured: 5M rows in 21.5 s
    "detect_overhead_s_per_1m": 1.5,
}

REGIONS = ["London", "South East", "Midlands", "North", "Scotland", "Ireland"]
REGION_WEIGHTS = [0.24, 0.20, 0.18, 0.18, 0.10, 0.10]
TOWNS = {
    "London": ["Oxford St", "Stratford", "Croydon", "Wembley", "Bromley", "Kingston"],
    "South East": ["Brighton", "Reading", "Guildford", "Southampton", "Canterbury", "Milton Keynes"],
    "Midlands": ["Birmingham", "Leicester", "Nottingham", "Coventry", "Derby", "Wolverhampton"],
    "North": ["Leeds", "Manchester", "Liverpool", "Newcastle", "Sheffield", "York"],
    "Scotland": ["Glasgow", "Edinburgh", "Aberdeen", "Dundee", "Inverness", "Stirling"],
    "Ireland": ["Dublin", "Belfast", "Cork", "Galway", "Limerick", "Derry"],
}
STORE_FORMATS = ["high_street", "retail_park", "flagship", "outlet"]
CATEGORIES = ["womenswear", "menswear", "kidswear", "footwear", "accessories", "beauty", "home", "nightwear"]
CATEGORY_SHARE = [0.22, 0.14, 0.14, 0.09, 0.11, 0.10, 0.12, 0.08]
CATEGORY_COST = {  # median unit cost in GBP
    "womenswear": 6.0, "menswear": 6.5, "kidswear": 4.0, "footwear": 9.0,
    "accessories": 2.5, "beauty": 2.2, "home": 4.5, "nightwear": 4.0,
}
ANOMALY_TYPES = [
    "none", "theft_external", "theft_internal", "scan_fraud", "counting_error",
    "receiving_error", "data_entry_error", "velocity_shift",
]
LP_FLAG_TYPES = ["theft", "counting_error", "process_issue", "data_error"]


def ensure_dirs() -> None:
    for d in (DATA_DIR, DATASETS_DIR, MODELS_DIR, RUNS_DIR, TRIAGE_DIR, EXPORTS_DIR, CONNECTORS_DIR):
        d.mkdir(parents=True, exist_ok=True)
