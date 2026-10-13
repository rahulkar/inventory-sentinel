"""Plain-language labels and the glossary, shared by the UI metadata, tools and the assistant's knowledge base."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

FEATURE_LABELS: dict[str, str] = {
    # raw daily columns
    "date_idx": "Date",
    "store_code": "Store",
    "sku_code": "SKU",
    "opening_stock": "Opening stock",
    "received_units": "Units received",
    "sold_units": "Units sold",
    "returned_units": "Units returned",
    "transfer_in_units": "Transferred in",
    "transfer_out_units": "Transferred out",
    "adjustment_units": "Recorded adjustment",
    "expected_closing": "Expected closing stock",
    "counted_closing": "Counted closing stock",
    "pos_scans": "Till scans",
    "manual_entry_scans": "Manually keyed scans",
    "void_count": "Voided lines",
    "override_count": "Price/quantity overrides",
    "after_hours_scans": "After-hours scans",
    "receiving_scans": "Units scanned at receiving",
    "on_promo": "On promotion",
    # detection features
    "shrinkage_pct": "Shrinkage % today",
    "variance_z_series": "Today's stock gap vs this item's normal",
    "shrink_sum_7_z": "Stock missing over 7 days (vs count noise)",
    "shrink_pct_7": "Shrinkage % over 7 days",
    "reversal_index": "Gap that reversed yesterday's (count error sign)",
    "velocity_z": "Sales vs normal (promotion-adjusted)",
    "zero_sales_streak": "Missed sales during a no-sales run",
    "receiving_gap_units": "Delivery booked vs scanned",
    "received_vs_typical": "Delivery size vs normal",
    "adjustment_vs_typical": "Adjustment size vs normal",
    "returns_z": "Returns vs normal",
    "manual_entry_z": "Manually keyed scans vs the store's habit",
    "void_z": "Voids vs the store's habit",
    "override_z": "Overrides vs the store's habit",
    "after_hours_z": "After-hours scans vs normal",
    "store_day_shrink_z": "Store-wide shrink that day vs normal",
    # context
    "variance_units": "Stock gap (units, log)",
    "variance_value": "Stock gap (£, log)",
    "stock_cover_days": "Days of stock on hand",
    "is_delivery_day": "Delivery day",
    "log_unit_cost": "Unit cost (log)",
    "dow": "Day of week",
    "category": "Category",
    # answer key
    "truth_type": "Answer key: anomaly type",
    "truth_incident": "Answer key: incident id",
    "truth_loss_units": "Answer key: units lost",
}

MODEL_PLAIN: dict[str, str] = {
    "zscore": "Rule of thumb: flags days whose shrinkage is far from normal for the category (the baseline to beat).",
    "iforest": "Isolation forest: isolates odd days with random splits; unusual days need fewer splits.",
    "autoencoder": "Autoencoder: a small neural network learns to rebuild normal days; days it cannot rebuild are unusual.",
    "lof": "Local outlier factor: compares how crowded a day's neighbourhood is with its neighbours' neighbourhoods.",
    "ensemble": "Ensemble: runs Isolation Forest and Local Outlier Factor together and adds how surprising each finds the day; they miss different problems.",
    "reranker": "Feedback re-ranker: a base detector plus a model trained on what investigators confirmed.",
}

TYPE_LABEL: dict[str, str] = {
    "theft_external": "External theft",
    "theft_internal": "Internal theft",
    "scan_fraud": "Till / scan fraud",
    "counting_error": "Counting error",
    "receiving_error": "Receiving error",
    "data_entry_error": "Data-entry error",
    "velocity_shift": "Sales pattern change",
    "unclear": "Unclear",
    "none": "Normal",
}
SEVERITY_LABEL = {"medium": "Medium", "high": "High", "critical": "Critical"}
OUTCOME_LABEL = {"confirmed_theft": "Confirmed theft", "counting_error": "Counting error", "process_issue": "Process issue", "false_alarm": "False alarm"}


def money(v: float) -> str:
    return f"£{v:,.0f}"


def plain_ap(ap: float | None, baseline: float | None = None) -> str:
    if ap is None:
        return "not measured (no labels)"
    s = f"average precision {ap:.2f}"
    if baseline:
        s += f" ({ap / baseline:.1f}x the rule of thumb)"
    return s


@dataclass
class GlossaryEntry:
    term: str
    plain: str
    detail: str
    aliases: list[str] = field(default_factory=list)


GLOSSARY: list[GlossaryEntry] = [
    GlossaryEntry("Shrinkage", "Stock that disappears without being sold: theft, damage, admin mistakes.", "Measured each day as expected closing stock minus counted closing stock. Shrinkage % divides by expected stock.", ["shrink", "stock loss", "shrinkage %", "shrinkage pct"]),
    GlossaryEntry("Variance", "The gap between what the system expects and what was counted.", "expected_closing - counted_closing. Positive means stock is missing. Count noise reverses the next day, so a 7-day sum keeps genuine loss.", ["stock gap", "stock variance"]),
    GlossaryEntry("Expected vs counted closing", "What the books say should be on the shelf versus what the evening count found.", "Expected = opening + received + returns + transfers in - sold - transfers out + adjustments. The count resets the books every morning.", ["expected closing", "counted closing", "book stock"]),
    GlossaryEntry("Velocity", "How fast an item sells compared with its own normal, allowing for promotions.", "velocity_z is a Poisson-style z-score of today's sales against the 28-day promotion-adjusted rate.", ["sales velocity", "velocity change"]),
    GlossaryEntry("Sweethearting", "A cashier lets goods through without charging, usually for friends.", "Shows as more voids, overrides and manually keyed scans than the store normally has, plus stock going missing.", ["scan fraud", "till fraud"]),
    GlossaryEntry("Refund fraud", "Fake returns: refunds are recorded but nothing comes back to the shelf.", "Returns rise without matching stock, so the books overstate stock and the count comes up short.", ["return fraud"]),
    GlossaryEntry("Phantom stock", "The system says an item is in stock, but it is not where shoppers can buy it.", "Sales drop to zero while stock is recorded; zero_sales_streak measures the sales that went missing.", ["zero sales", "phantom inventory"]),
    GlossaryEntry("Counting error", "A miscount that the next count corrects.", "A gap one day followed by the opposite gap the next; reversal_index catches the pattern.", ["miscount", "count error"]),
    GlossaryEntry("Receiving discrepancy", "A delivery booked in at a different quantity from what arrived.", "Compare received units with units scanned at receiving; a short delivery shows as missing stock on the delivery day.", ["receiving error", "delivery error"]),
    GlossaryEntry("Loss-prevention flag", "A past incident that the loss-prevention team recorded.", "LP flags are partial (most incidents were never flagged) and noisy (some are wrong). They are used as a lower-bound check, never as the only truth.", ["lp flag", "lp flags", "loss prevention"]),
    GlossaryEntry("Isolation forest", "A method that isolates unusual days with random splits; odd days need fewer splits.", "Unsupervised; trained on history without labels. Score = 2^(-average path length / expected path length).", ["iforest", "isolation"]),
    GlossaryEntry("Autoencoder", "A small neural network that learns to rebuild normal days; days it cannot rebuild are unusual.", "Score = mean squared reconstruction error of the standardised features.", ["ae", "neural network"]),
    GlossaryEntry("Local outlier factor", "Compares how crowded a day's neighbourhood is with its neighbours'.", "LOF > 1 means the point sits in a sparser region than its neighbours. Scored against a fixed reference sample.", ["lof"]),
    GlossaryEntry("Ensemble", "Runs Isolation Forest and Local Outlier Factor together and adds how surprising each finds the day.", "Each score becomes -log P(a normal training day scores at least this high); the two are summed. They miss different problems, so the sum ranks real ones higher than either alone.", ["ensemble", "combined model"]),
    GlossaryEntry("Robust z-score", "How many 'typical deviations' a value is from the median.", "z = (x - median) / (1.4826 x MAD). Unlike the mean and standard deviation, one extreme value does not distort it.", ["robust z", "mad", "median absolute deviation"]),
    GlossaryEntry("Alert rate", "The share of days the model is allowed to flag.", "The alert threshold is set so that this share of training days score above it (0.8% by default).", ["contamination", "threshold"]),
    GlossaryEntry("Average precision", "How well the ranking puts real problems at the top; 1.0 is perfect.", "Area under the precision-recall curve on the evaluation window, using the demo vendor's answer key (or LP flags). Random ranking scores the share of real days (about 0.006 on the demo data), not 0.5; and about a quarter of labelled days carry no visible signal, so even a supervised model given the answer key reaches only about 0.75.", ["ap", "pr-auc", "pr auc"]),
    GlossaryEntry("ROC-AUC", "The chance a real problem scores higher than a normal day.", "0.5 is random, 1.0 is perfect; it is generous when problems are rare, so average precision leads.", ["auc", "roc"]),
    GlossaryEntry("Precision at k", "Of the top k alerts, how many are real.", "precision@1000 = real problems among the 1,000 highest-scoring days in the evaluation window.", ["precision@k", "precision at 1000"]),
    GlossaryEntry("Recall", "Of all real problems, how many the alerts caught.", "Incident recall counts an incident as caught if any of its days was flagged.", ["incident recall", "detection rate"]),
    GlossaryEntry("Severity", "How unusual the alert is: medium, high or critical.", "Medium above the alert threshold, high above the 99.8th training percentile, critical above the 99.95th.", ["critical", "priority"]),
    GlossaryEntry("Incident", "Consecutive flagged days for the same item in the same store, grouped into one alert.", "Gaps of one quiet day are bridged. Each incident has a stable key store|sku|start date so feedback carries across runs.", ["alert", "alerts"]),
    GlossaryEntry("Value at risk", "The cost of the stock that went missing during the incident.", "Sum of positive daily gaps times unit cost (valued at cost, not retail price).", ["£ at risk", "value at risk gbp"]),
    GlossaryEntry("P(true anomaly)", "The chance an alert is a real problem, given its score.", "Calibrated by score band from team feedback, a demo vendor's answer key, LP flags or a stated prior (in that order).", ["p_true", "calibration", "probability"]),
    GlossaryEntry("Investigation planner", "Turns investigator hours into a ranked work list with an expected return.", "Expected value = P(true) x (value at risk x recovery rate + daily loss x horizon x persistence). Ranked by expected value per hour.", ["planner", "investigation roi", "breakeven hours", "roi"]),
    GlossaryEntry("Triage", "Teams mark each alert: confirmed theft, counting error, process issue or false alarm.", "Decisions are keyed to the alert, carry across runs, recalibrate P(true) and can train the feedback re-ranker.", ["feedback", "triage outcomes", "false alarm"]),
    GlossaryEntry("Feedback re-ranker", "Learns from what investigators confirmed to put likely real problems first.", "LightGBM trained on triage outcomes and LP flags, blended with the base detector's percentile. Judged on days no one reviewed.", ["re-ranker", "reranker", "retrain"]),
]


def explain(term: str) -> GlossaryEntry | None:
    q = (term or "").strip().lower()
    if not q:
        return None
    for e in GLOSSARY:
        if q == e.term.lower() or q in [a.lower() for a in e.aliases]:
            return e
    for e in GLOSSARY:
        if q in e.term.lower() or any(q in a.lower() or a.lower() in q for a in e.aliases):
            return e
    if q in FEATURE_LABELS:
        return GlossaryEntry(q, FEATURE_LABELS[q], "A field in the inventory data or a feature the models use.")
    names = [e.term.lower() for e in GLOSSARY] + [a.lower() for e in GLOSSARY for a in e.aliases]
    close = difflib.get_close_matches(q, names, n=1, cutoff=0.6)
    if close:
        for e in GLOSSARY:
            if close[0] == e.term.lower() or close[0] in [a.lower() for a in e.aliases]:
                return e
    return None


def glossary_markdown() -> str:
    lines = ["# Glossary", ""]
    for e in GLOSSARY:
        lines += [f"## {e.term}", e.plain, e.detail]
        if e.aliases:
            lines.append("Also called: " + ", ".join(e.aliases))
        lines.append("")
    lines.append("## Fields and features")
    lines += [f"- {k}: {v}" for k, v in FEATURE_LABELS.items()]
    lines += ["", "## Methods"] + [f"- {k}: {v}" for k, v in MODEL_PLAIN.items()]
    lines += ["", "## Anomaly types"] + [f"- {k}: {v}" for k, v in TYPE_LABEL.items()]
    return "\n".join(lines)
