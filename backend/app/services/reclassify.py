"""AI assist for alerts the rules could not type: ask the configured LLM gateway for the most likely cause.

The rule label (`likely_type`) stays as it is. Suggestions live beside the run in ai_types.json, keyed by alert key,
and the executive view counts a case under the AI's type when the model was confident enough."""
from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import Any

import httpx
import numpy as np
import pandas as pd

from app import config
from app.assistant import settings as llm_settings
from app.assistant import usage
from app.services import explain, storage
from app.services import features as F

TYPES = config.ANOMALY_TYPES[1:]  # everything but "none"
TYPE_GUIDE = {
    "theft_external": "stock going missing over several days without matching sales",
    "theft_internal": "losses with after-hours scans, or several items going missing in one store on the same day",
    "scan_fraud": "voids, price/quantity overrides, keyed-in items or refunds well above the store's habit",
    "counting_error": "a gap one day that the next count reverses; net change small",
    "receiving_error": "a delivery booked at a different quantity from what was scanned in",
    "data_entry_error": "a quantity typed far too large (e.g. ten times) or with the wrong sign, in a receipt or adjustment",
    "velocity_shift": "sales stop while the books show stock (phantom stock) or jump with no promotion; little stock actually missing",
}
MIN_CONFIDENCE = 0.5  # below this the case stays "unclear" on the dashboard
BATCH = 20
CONCURRENCY = 4
MAX_CASES = 200  # per request, highest revenue at risk first
RAW_COLS = ["expected_closing", "counted_closing", "sold_units", "received_units", "receiving_scans", "adjustment_units", "returned_units", "manual_entry_scans", "pos_scans", "void_count", "override_count", "after_hours_scans"]

_lock = threading.Lock()


def _path(run_id: str):
    return storage.run_dir(run_id) / "ai_types.json"


def load(run_id: str) -> dict[str, dict[str, Any]]:
    p = _path(run_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def version(run_id: str) -> float:
    p = _path(run_id)
    return p.stat().st_mtime if p.exists() else 0.0


def effective_types(run_id: str, inc: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(type to report, whether that type came from the AI) for each incident row."""
    ai = load(run_id)
    if not len(inc):
        return pd.Series(dtype=str), pd.Series(dtype=bool)
    def pick(row: pd.Series) -> str:
        s = ai.get(row["alert_key"]) if row["likely_type"] == "unclear" else None
        return s["type"] if s and s.get("type") in TYPES and float(s.get("confidence", 0)) >= MIN_CONFIDENCE else row["likely_type"]
    eff = inc.apply(pick, axis=1).astype(str)
    return eff, eff != inc["likely_type"]


def _case(i: int, row: pd.Series, ds: storage.Dataset, baseline: dict[str, Any]) -> dict[str, Any]:
    pr = int(row["peak_row"])
    feat = {f: float(np.asarray(ds.features[f])[pr]) for f in F.DETECT_FEATURES}
    raw = {c: int(np.asarray(ds.daily[c])[pr]) for c in RAW_COLS if c in ds.daily}
    dev = explain.deviations(feat, baseline, str(row["category"])) if baseline else {}
    return {
        "id": i,
        "category": row["category"],
        "days_flagged": int(row["n_days"]),
        "units_missing": int(row["units_at_risk"]),
        "net_variance_units": int(row["net_variance_units"]),
        "peak_day": raw,
        # robust z-scores against the item's category; only the notable ones
        "signal_z": {f: round(z, 1) for f, z in sorted(dev.items(), key=lambda kv: -abs(kv[1]))[:8] if abs(z) >= 1.0},
        "detector_notes": [x for x in str(row.get("reasons", "")).split(" || ") if x],
    }


def _prompt(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    guide = "\n".join(f"- {t}: {d}" for t, d in TYPE_GUIDE.items())
    system = (
        "You triage retail stock-loss alerts. Each case is a store-item whose counted stock drifted from the books. "
        "Fixed rules could not tell what caused it. Pick the single most likely cause from this list:\n"
        f"{guide}\n- unclear: the evidence does not point to any one cause\n\n"
        "Use only the numbers given. Confidence is 0-1; use below 0.5 when two causes are about equally likely. "
        'Answer with JSON only: {"results": [{"id": <id>, "type": "<cause>", "confidence": <0-1>, "why": "<one short sentence>"}]}, one entry per case.'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"cases": cases}, separators=(",", ":"))}]


def _parse(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return []
    return [r for r in data.get("results", []) if isinstance(r, dict)]


async def _call(client: httpx.AsyncClient, s: llm_settings.LlmSettings, cases: list[dict[str, Any]], sem: asyncio.Semaphore) -> list[dict[str, Any]]:
    async with sem:
        r = await client.post(
            f"{s.base_url}/v1/chat/completions",
            headers=llm_settings._headers(s.api_key),
            json={"model": s.model, "messages": _prompt(cases), "temperature": 0, "max_tokens": 4096, "response_format": {"type": "json_object"}},
        )
        r.raise_for_status()
        data = r.json()
    u = data.get("usage") or {}
    usage.record_llm_call(
        session_id="reclassify", turn_id=storage.new_id("rc"), agent="reclassify", model=s.model,
        prompt_tokens=int(u.get("prompt_tokens") or 0), completion_tokens=int(u.get("completion_tokens") or 0),
        price=usage.resolve_price(s.base_url, s.model, s.price_input_per_m, s.price_output_per_m),
    )
    return _parse(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")


def candidates(rd: storage.RunData, ds: storage.Dataset, open_keys: set[str] | None, redo: bool = False) -> pd.DataFrame:
    """Open unclear cases without a suggestion yet, highest revenue at risk first."""
    inc = rd.incidents
    if not len(inc):
        return inc
    c = inc[inc["likely_type"] == "unclear"]
    if open_keys is not None:
        c = c[c["alert_key"].isin(open_keys)]
    if not redo:
        done = load(rd.run.run_id)
        c = c[~c["alert_key"].isin(done)]
    price_col = "unit_price" if "unit_price" in ds.skus else "unit_cost"
    price = dict(zip(ds.skus["sku_id"], ds.skus[price_col].astype(float)))
    rev = c["units_at_risk"].astype(float) * c["sku_id"].map(price).fillna(0.0)
    return c.assign(_rev=rev).sort_values("_rev", ascending=False).drop(columns="_rev")


async def run(run_id: str, alert_keys: list[str] | None = None, redo: bool = False) -> dict[str, Any]:
    s = llm_settings.load()
    if not s.configured:
        raise ValueError("Set up the AI gateway in Settings first.")
    rd = storage.load_run(run_id)
    ds = storage.load_dataset(rd.run.dataset_id)
    from app.services import triage

    reviews = triage.latest(ds.meta.id)
    open_keys = {k for k in rd.incidents["alert_key"] if k not in reviews} if len(rd.incidents) else set()
    if alert_keys is not None:
        open_keys &= set(alert_keys)
    todo = candidates(rd, ds, open_keys, redo).head(MAX_CASES)
    if not len(todo):
        return {"requested": 0, "reclassified": 0, "still_unclear": 0, "failed": 0}
    model = storage.get_model(rd.run.model_id)
    baseline = model.feature_baseline if model else {}
    rows = list(todo.iterrows())
    cases = [_case(i, r, ds, baseline) for i, (_, r) in enumerate(rows)]
    sem = asyncio.Semaphore(CONCURRENCY)
    verify = llm_settings.verify_arg(s.verify_ssl, s.ca_bundle)
    async with httpx.AsyncClient(timeout=s.timeout_s, verify=verify) as client:
        out = await asyncio.gather(*(_call(client, s, cases[k:k + BATCH], sem) for k in range(0, len(cases), BATCH)), return_exceptions=True)
    errors = [o for o in out if isinstance(o, Exception)]
    if errors and len(errors) == len(out):
        raise RuntimeError(llm_settings.readable_error(errors[0], s.base_url))
    now = storage.now_iso()
    got: dict[str, dict[str, Any]] = {}
    for batch in out:
        if isinstance(batch, Exception):
            continue
        for r in batch:
            try:
                i = int(r["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if not 0 <= i < len(rows):
                continue
            t = str(r.get("type", "unclear"))
            conf = min(1.0, max(0.0, float(r.get("confidence") or 0)))
            got[rows[i][1]["alert_key"]] = {"type": t if t in TYPES else "unclear", "confidence": round(conf, 2), "why": str(r.get("why", ""))[:300], "model": s.model, "at": now}
    with _lock:
        merged = {**load(run_id), **got}
        storage.atomic_write_text(_path(run_id), json.dumps(merged, indent=1))
    moved = sum(1 for v in got.values() if v["type"] != "unclear" and v["confidence"] >= MIN_CONFIDENCE)
    return {"requested": len(rows), "reclassified": moved, "still_unclear": len(got) - moved, "failed": len(rows) - len(got)}
