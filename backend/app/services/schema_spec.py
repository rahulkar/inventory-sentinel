"""The inventory column schema shared by imports, connector syncs and the column store.

Daily rows are one SKU in one store on one day. The `truth_*` columns are an optional answer key that only a demo
vendor (or one of our own exports) can supply; they are never model features.
"""
from __future__ import annotations

from typing import Any

import numpy as np

DAILY_SPECS: dict[str, Any] = {
    "date_idx": np.int16,
    "store_code": np.int16,
    "sku_code": np.int16,
    "opening_stock": np.int32,
    "received_units": np.int16,
    "sold_units": np.int16,
    "returned_units": np.int16,
    "transfer_in_units": np.int16,
    "transfer_out_units": np.int16,
    "adjustment_units": np.int16,
    "expected_closing": np.int32,
    "counted_closing": np.int32,
    "pos_scans": np.int16,
    "manual_entry_scans": np.int16,
    "void_count": np.int16,
    "override_count": np.int16,
    "after_hours_scans": np.int16,
    "receiving_scans": np.int16,
    "on_promo": np.int8,
}
TRUTH_SPECS: dict[str, Any] = {"truth_type": np.int8, "truth_incident": np.int32, "truth_loss_units": np.int16}
MEASURES = [c for c in DAILY_SPECS if c not in ("date_idx", "store_code", "sku_code")]
LP_COLUMNS = ["flag_id", "date", "store_id", "sku_id", "date_idx", "store_code", "sku_code", "flag_type", "source", "confirmed", "loss_value_gbp"]
