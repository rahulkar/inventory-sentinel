"""Disk persistence: registry.json, dataset folders (column store), model artefacts, detection runs.

Layout under data/:
  datasets/ds_xxx/{meta.json, daily/*.npy, features/*.npy, truth/*.npy, index.npz, stores.csv, skus.csv, lp_flags.csv}
  models/m_xxx.{joblib, json, onnx, onnx.json}
  runs/run_xxx/{run.json, score.npy, percentile.npy, severity.npy, incidents.csv, aggregates.json}
  triage/ds_xxx.jsonl, exports/ds_xxx.zip, exports/models/m_xxx.zip
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app import config
from app.schemas import DatasetMeta, DetectionRun, DetectionRunSummary, ExportStatus, ModelMeta, ModelSummary
from app.services import colstore

_lock = threading.RLock()
_registry: dict[str, Any] | None = None


class _LRU:
    def __init__(self, maxsize: int) -> None:
        self.maxsize = maxsize
        self._d: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any | None:
        with _lock:
            if key in self._d:
                self._d.move_to_end(key)
                return self._d[key]
            return None

    def put(self, key: str, value: Any) -> None:
        with _lock:
            self._d[key] = value
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def pop(self, key: str) -> None:
        with _lock:
            self._d.pop(key, None)

    def clear(self) -> None:
        with _lock:
            self._d.clear()


_dataset_cache = _LRU(config.CACHE_COLUMNS)
_pipe_cache = _LRU(config.CACHE_PIPELINES)
_run_cache = _LRU(config.CACHE_RUNS)


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


_ID_RE = re.compile(r"[a-z]+_[0-9a-f]{8}")


def check_id(value: str) -> str:
    """Ids from URLs and query strings become file names: only accept the `new_id` shape (no "..", slashes or drives)."""
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise LookupError(f"Unknown id {value!r}")
    return value


def safe_name(name: str, n: int = 40) -> str:
    return ("".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:n]).strip("_") or "dataset"


# ---------------------------------------------------------------- file helpers
def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def safe_unlink(path: Path, retries: int = 5, delay: float = 0.4) -> bool:
    """Delete a file, retrying on Windows share violations (AV scans, in-flight downloads)."""
    for i in range(retries):
        try:
            if path.exists():
                path.unlink()
            return True
        except PermissionError:
            if i == retries - 1:
                return False
            time.sleep(delay)
        except OSError:
            return False
    return True


def safe_rmtree(path: Path, retries: int = 5, delay: float = 0.4) -> bool:
    """Remove a folder; memory-mapped files may hold handles briefly on Windows, so drop caches and retry."""
    for i in range(retries):
        if not path.exists():
            return True
        try:
            shutil.rmtree(path)
            return True
        except (PermissionError, OSError):
            import gc

            gc.collect()
            if i == retries - 1:
                return False
            time.sleep(delay)
    return not path.exists()


def file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


# ---------------------------------------------------------------- registry
def _load_registry() -> dict[str, Any]:
    global _registry
    if _registry is None:
        loaded = None
        if config.REGISTRY_PATH.exists():
            try:
                loaded = json.loads(config.REGISTRY_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                loaded = None
        if not isinstance(loaded, dict):
            loaded = {}
        loaded.setdefault("datasets", {})
        loaded.setdefault("models", {})
        loaded.setdefault("runs", {})
        loaded.setdefault("active_model_id", None)
        _registry = loaded
    return _registry


def _save_registry() -> None:
    reg = _load_registry()
    config.ensure_dirs()
    atomic_write_text(config.REGISTRY_PATH, json.dumps(reg, indent=1))


# ---------------------------------------------------------------- datasets
def dataset_dir(ds_id: str) -> Path:
    return config.DATASETS_DIR / check_id(ds_id)


def export_path(ds_id: str) -> Path:
    return config.EXPORTS_DIR / f"{ds_id}.zip"


@dataclass
class Dataset:
    """A loaded dataset: small tables in memory, big columns memory-mapped."""

    meta: DatasetMeta
    stores: pd.DataFrame
    skus: pd.DataFrame
    dates: np.ndarray
    series_offsets: np.ndarray
    series_store: np.ndarray
    series_sku: np.ndarray
    lp_flags: pd.DataFrame
    daily: dict[str, np.ndarray] = field(default_factory=dict)
    features: dict[str, np.ndarray] = field(default_factory=dict)
    truth: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return dataset_dir(self.meta.id)

    @property
    def test_from_idx(self) -> int:
        return int(np.searchsorted(self.dates, self.meta.test_from_date))

    def series_index(self, store_id: str, sku_id: str) -> int | None:
        st = np.flatnonzero(self.stores["store_id"].to_numpy() == store_id)
        sk = np.flatnonzero(self.skus["sku_id"].to_numpy() == sku_id)
        if not len(st) or not len(sk):
            return None
        hit = np.flatnonzero((self.series_store == st[0]) & (self.series_sku == sk[0]))
        return int(hit[0]) if len(hit) else None

    def lp_mask(self) -> np.ndarray:
        """Boolean row mask of rows that carry a loss-prevention flag."""
        mask = np.zeros(self.meta.n_rows, dtype=bool)
        if len(self.lp_flags):
            rows = flag_rows(self, self.lp_flags)
            mask[rows[rows >= 0]] = True
        return mask


def flag_rows(ds: Dataset, flags: pd.DataFrame) -> np.ndarray:
    """Row index of each flag (store_code, sku_code, date_idx), -1 when the series/day is not present."""
    if not len(flags):
        return np.zeros(0, dtype=np.int64)
    key = ds.series_store.astype(np.int64) * 100_000 + ds.series_sku.astype(np.int64)
    order = np.argsort(key)
    fk = flags["store_code"].to_numpy().astype(np.int64) * 100_000 + flags["sku_code"].to_numpy().astype(np.int64)
    pos = np.searchsorted(key[order], fk)
    pos = np.clip(pos, 0, len(order) - 1)
    ok = key[order][pos] == fk
    series = order[pos]
    day = flags["date_idx"].to_numpy().astype(np.int64)
    out = np.full(len(flags), -1, dtype=np.int64)
    for i in np.flatnonzero(ok):  # flags are few; binary search inside the series (works with date gaps)
        a, b = int(ds.series_offsets[series[i]]), int(ds.series_offsets[series[i] + 1])
        j = a + int(np.searchsorted(ds.daily["date_idx"][a:b], day[i]))
        if j < b and int(ds.daily["date_idx"][j]) == day[i]:
            out[i] = j
    return out


def register_dataset(meta: DatasetMeta) -> None:
    meta.size_bytes = colstore.dir_size(dataset_dir(meta.id))
    atomic_write_text(dataset_dir(meta.id) / "meta.json", meta.model_dump_json(indent=1))
    with _lock:
        reg = _load_registry()
        reg["datasets"][meta.id] = meta.model_dump()
        _save_registry()
    _dataset_cache.pop(meta.id)


def list_datasets() -> list[DatasetMeta]:
    with _lock:
        items = [DatasetMeta(**d) for d in _load_registry()["datasets"].values()]
    return sorted(items, key=lambda d: d.created_at, reverse=True)


def get_dataset_meta(ds_id: str) -> DatasetMeta | None:
    with _lock:
        d = _load_registry()["datasets"].get(ds_id)
    return DatasetMeta(**d) if d else None


def load_dataset(ds_id: str, with_truth: bool = True) -> Dataset:
    cached = _dataset_cache.get(ds_id)
    if cached is not None:
        return cached
    meta = get_dataset_meta(ds_id)
    if meta is None:
        raise LookupError(f"Dataset {ds_id} not found")
    base = dataset_dir(ds_id)
    idx = colstore.load_index(base / "index.npz")
    lp = pd.read_csv(base / "lp_flags.csv") if (base / "lp_flags.csv").exists() else pd.DataFrame(columns=["flag_id", "date", "store_id", "sku_id", "date_idx", "store_code", "sku_code", "flag_type", "source", "confirmed", "loss_value_gbp"])
    ds = Dataset(
        meta=meta,
        stores=pd.read_csv(base / "stores.csv", dtype={"store_id": str, "store_name": str, "region": str, "warehouse_team": str}),
        skus=pd.read_csv(base / "skus.csv", dtype={"sku_id": str, "sku_name": str, "category": str}),
        dates=idx["dates"].astype(str),
        series_offsets=idx["series_offsets"],
        series_store=idx["series_store"],
        series_sku=idx["series_sku"],
        lp_flags=lp,
        daily=colstore.open_columns(base / "daily"),
        features=colstore.open_columns(base / "features"),
        truth=colstore.open_columns(base / "truth") if (with_truth and (base / "truth").exists()) else {},
    )
    _dataset_cache.put(ds_id, ds)
    return ds


def delete_dataset(ds_id: str) -> bool:
    with _lock:
        reg = _load_registry()
        if ds_id not in reg["datasets"]:
            return False
        del reg["datasets"][ds_id]
        runs = [r for r, v in reg["runs"].items() if v.get("dataset_id") == ds_id]
        for r in runs:
            del reg["runs"][r]
        _save_registry()
    _dataset_cache.pop(ds_id)
    for r in runs:
        _run_cache.pop(r)
        safe_rmtree(config.RUNS_DIR / r)
    import gc

    gc.collect()
    safe_rmtree(dataset_dir(ds_id))
    safe_unlink(export_path(ds_id))
    safe_unlink(config.TRIAGE_DIR / f"{ds_id}.jsonl")
    return True


def export_status(ds_id: str) -> ExportStatus:
    p = export_path(ds_id)
    if p.exists():
        return ExportStatus(dataset_id=ds_id, ready=True, size_bytes=file_size(p), created_at=datetime.fromtimestamp(p.stat().st_mtime).replace(microsecond=0).isoformat())
    return ExportStatus(dataset_id=ds_id, ready=False)


# ---------------------------------------------------------------- models
def model_paths(model_id: str) -> dict[str, Path]:
    check_id(model_id)
    return {
        "pipeline": config.MODELS_DIR / f"{model_id}.joblib",
        "meta": config.MODELS_DIR / f"{model_id}.json",
        "onnx": config.MODELS_DIR / f"{model_id}.onnx",
        "onnx_meta": config.MODELS_DIR / f"{model_id}.onnx.json",
        "bundle": config.EXPORTS_DIR / "models" / f"{model_id}.zip",
    }


def save_model(meta: ModelMeta, pipeline: Any) -> None:
    config.ensure_dirs()
    paths = model_paths(meta.model_id)
    joblib.dump(pipeline, paths["pipeline"])
    atomic_write_text(paths["meta"], meta.model_dump_json(indent=1))
    with _lock:
        reg = _load_registry()
        reg["models"][meta.model_id] = ModelSummary(**meta.model_dump()).model_dump()
        _save_registry()
    _pipe_cache.put(meta.model_id, pipeline)


def update_model_meta(meta: ModelMeta) -> None:
    atomic_write_text(model_paths(meta.model_id)["meta"], meta.model_dump_json(indent=1))
    with _lock:
        reg = _load_registry()
        if meta.model_id in reg["models"]:
            reg["models"][meta.model_id] = ModelSummary(**meta.model_dump()).model_dump()
            _save_registry()


def _with_active(summary: dict[str, Any], active_id: str | None) -> dict[str, Any]:
    summary = dict(summary)
    summary["is_active"] = summary["model_id"] == active_id
    return summary


def list_models() -> list[ModelSummary]:
    with _lock:
        reg = _load_registry()
        active = reg["active_model_id"]
        items = [ModelSummary(**_with_active(m, active)) for m in reg["models"].values()]
    return sorted(items, key=lambda m: m.created_at, reverse=True)


def get_model_summary(model_id: str) -> ModelSummary | None:
    with _lock:
        reg = _load_registry()
        m = reg["models"].get(model_id)
        if not m:
            return None
        return ModelSummary(**_with_active(m, reg["active_model_id"]))


def get_model(model_id: str) -> ModelMeta | None:
    path = model_paths(model_id)["meta"]
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    with _lock:
        data["is_active"] = _load_registry()["active_model_id"] == model_id
    return ModelMeta(**data)


def load_pipeline(model_id: str) -> Any:
    cached = _pipe_cache.get(model_id)
    if cached is not None:
        return cached
    pipe = joblib.load(model_paths(model_id)["pipeline"])
    _pipe_cache.put(model_id, pipe)
    return pipe


def set_active_model(model_id: str | None) -> None:
    with _lock:
        reg = _load_registry()
        reg["active_model_id"] = model_id
        _save_registry()


def get_active_model_id() -> str | None:
    with _lock:
        return _load_registry()["active_model_id"]


def delete_model(model_id: str) -> bool:
    with _lock:
        reg = _load_registry()
        if model_id not in reg["models"]:
            return False
        del reg["models"][model_id]
        if reg["active_model_id"] == model_id:
            reg["active_model_id"] = None
        _save_registry()
    _pipe_cache.pop(model_id)
    for p in model_paths(model_id).values():
        safe_unlink(p)
    return True


# ---------------------------------------------------------------- detection runs
INCIDENT_COLUMNS = [
    "alert_id", "alert_key", "store_code", "sku_code", "store_id", "store_name", "region", "warehouse_team", "sku_id", "sku_name", "category",
    "start_date", "end_date", "n_days", "n_flagged_days", "peak_row", "peak_score", "peak_percentile", "severity", "units_at_risk",
    "value_at_risk_gbp", "net_variance_units", "likely_type", "type_confidence", "reasons", "p_true", "truth_type", "start_day",
]
_INCIDENT_TEXT = {c: str for c in ("alert_id", "alert_key", "store_id", "store_name", "region", "warehouse_team", "sku_id", "sku_name", "category", "reasons", "truth_type")}


def run_dir(run_id: str) -> Path:
    return config.RUNS_DIR / check_id(run_id)


@dataclass
class RunData:
    run: DetectionRun
    score: np.ndarray
    percentile: np.ndarray
    severity: np.ndarray
    incidents: pd.DataFrame
    aggregates: dict[str, Any]


def save_run(run: DetectionRun, columns: dict[str, np.ndarray], incidents: pd.DataFrame, aggregates: dict[str, Any]) -> None:
    d = run_dir(run.run_id)
    d.mkdir(parents=True, exist_ok=True)
    for k, v in columns.items():
        np.save(d / f"{k}.npy", v, allow_pickle=False)
    incidents.to_csv(d / "incidents.csv", index=False)
    atomic_write_text(d / "aggregates.json", json.dumps(aggregates))
    atomic_write_text(d / "run.json", run.model_dump_json(indent=1))
    with _lock:
        reg = _load_registry()
        reg["runs"][run.run_id] = DetectionRunSummary(
            run_id=run.run_id, dataset_id=run.dataset_id, dataset_name=run.dataset_name, model_id=run.model_id, model_label=run.model_label,
            created_at=run.created_at, incidents=run.kpis.incidents, value_at_risk_gbp=run.kpis.value_at_risk_gbp,
        ).model_dump()
        _save_registry()
    _run_cache.pop(run.run_id)


def list_runs(dataset_id: str | None = None) -> list[DetectionRunSummary]:
    with _lock:
        reg = _load_registry()
        active = reg["active_model_id"]
        items = [DetectionRunSummary(**{**r, "model_in_use": r["model_id"] == active}) for r in reg["runs"].values()]
    if dataset_id:
        items = [r for r in items if r.dataset_id == dataset_id]
    return sorted(items, key=lambda r: r.created_at, reverse=True)


def load_run(run_id: str) -> RunData:
    cached = _run_cache.get(run_id)
    if cached is not None:
        return cached
    d = run_dir(run_id)
    if not (d / "run.json").exists():
        raise LookupError(f"Detection run {run_id} not found")
    try:
        # every text column as str: imported names default to their ids, and numeric-looking ones (EAN codes) would load as int
        inc = pd.read_csv(d / "incidents.csv", dtype=_INCIDENT_TEXT, keep_default_na=False)
    except pd.errors.EmptyDataError:  # runs saved with no incidents before the header was kept
        inc = pd.DataFrame(columns=INCIDENT_COLUMNS)
    data = RunData(
        run=DetectionRun(**json.loads((d / "run.json").read_text(encoding="utf-8"))),
        score=np.load(d / "score.npy", mmap_mode="r"),
        percentile=np.load(d / "percentile.npy", mmap_mode="r"),
        severity=np.load(d / "severity.npy", mmap_mode="r"),
        incidents=inc,
        aggregates=json.loads((d / "aggregates.json").read_text(encoding="utf-8")),
    )
    _run_cache.put(run_id, data)
    return data


def update_run_incidents(run_id: str, incidents: pd.DataFrame) -> None:
    incidents.to_csv(run_dir(run_id) / "incidents.csv", index=False)
    _run_cache.pop(run_id)


def delete_run(run_id: str) -> bool:
    with _lock:
        reg = _load_registry()
        if run_id not in reg["runs"]:
            return False
        del reg["runs"][run_id]
        _save_registry()
    _run_cache.pop(run_id)
    import gc

    gc.collect()
    safe_rmtree(run_dir(run_id))
    return True


# ---------------------------------------------------------------- maintenance
def sweep_orphans() -> list[str]:
    """Remove leftovers from interrupted jobs or deleted items. Called at startup."""
    config.ensure_dirs()
    removed: list[str] = []
    with _lock:
        reg = _load_registry()
        ds_ids, model_ids, run_ids = set(reg["datasets"]), set(reg["models"]), set(reg["runs"])
    for p in list(config.DATA_DIR.rglob("*.tmp")):
        if p.is_file() and safe_unlink(p):
            removed.append(str(p))
    for p in config.DATASETS_DIR.iterdir():
        if p.is_dir() and p.name not in ds_ids and safe_rmtree(p):
            removed.append(str(p))
    for p in config.RUNS_DIR.iterdir():
        if p.is_dir() and p.name not in run_ids and safe_rmtree(p):
            removed.append(str(p))
    for p in config.MODELS_DIR.glob("m_*"):
        if p.name.split(".")[0] not in model_ids and safe_unlink(p):
            removed.append(str(p))
    for p in config.EXPORTS_DIR.glob("ds_*.zip"):
        if p.stem not in ds_ids and safe_unlink(p):
            removed.append(str(p))
    for p in (config.EXPORTS_DIR / "models").glob("m_*.zip") if (config.EXPORTS_DIR / "models").exists() else []:
        if p.stem not in model_ids and safe_unlink(p):
            removed.append(str(p))
    return removed
