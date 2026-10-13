"""Domain constants for the demo vendor's simulated estate (a UK fashion and home retailer)."""
from __future__ import annotations

from typing import Any

import numpy as np

GEN_BLOCK_STORES = 10

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
