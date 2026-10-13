"""Settings for the demo vendor back-office (all from environment variables)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("VENDOR_MOCK_DATA_DIR") or ROOT / "data_vendor")
DB_PATH = DATA_DIR / "vendor.sqlite"

VENDOR_NAME = os.environ.get("VENDOR_MOCK_NAME", "Demo Retail Co.")
SYSTEM_NAME = "Demo back-office (simulated)"
PUBLIC_URL = os.environ.get("VENDOR_MOCK_PUBLIC_URL", "http://127.0.0.1:8020").rstrip("/")
TOKEN = os.environ.get("VENDOR_MOCK_TOKEN") or None  # when set, /mcp needs "Authorization: Bearer <token>"
TIMEZONE = os.environ.get("VENDOR_MOCK_TZ", "Europe/London")
CURRENCY = "GBP"

# the simulated estate: days before today are history, the rest is revealed one business day at a time
N_STORES = int(os.environ.get("VENDOR_MOCK_STORES", 40))
N_SKUS = int(os.environ.get("VENDOR_MOCK_SKUS", 250))
HISTORY_DAYS = int(os.environ.get("VENDOR_MOCK_HISTORY_DAYS", 150))
FUTURE_DAYS = int(os.environ.get("VENDOR_MOCK_FUTURE_DAYS", 120))
SEED = int(os.environ.get("VENDOR_MOCK_SEED", 7))
ANOMALY_MULTIPLIER = float(os.environ.get("VENDOR_MOCK_ANOMALY_MULTIPLIER", 1.0))
LP_COVERAGE = float(os.environ.get("VENDOR_MOCK_LP_COVERAGE", 0.4))

DEFAULT_PAGE_SIZE = 50_000
MAX_PAGE_SIZE = 100_000
CONTRACT = "sentinel-inventory-connector"
CONTRACT_VERSION = "1.0"
TASK_TYPES = ["recount", "investigate", "cctv_review", "receiving_check", "till_audit", "data_correction", "process_review"]
TASK_PRIORITIES = ["low", "normal", "high", "urgent"]
TASK_STATUSES = ["open", "acknowledged", "in_progress", "done", "rejected"]
TASK_OUTCOMES = ["confirmed_loss", "count_corrected", "process_fixed", "no_issue"]
