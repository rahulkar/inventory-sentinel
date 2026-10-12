"""Export a dataset as a ZIP bundle that the app (or any tool) can read: daily.csv + dimension tables + answer key."""
from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any

import numpy as np
import pandas as pd

from app import config
from app.schemas import Job
from app.services import jobs, storage

FORMAT = "inventory-sentinel-dataset"


def _daily_frame(ds: storage.Dataset, a: int, b: int) -> pd.DataFrame:
    d = {k: np.asarray(v[a:b]) for k, v in ds.daily.items()}
    out = pd.DataFrame({
        "date": ds.dates[d["date_idx"].astype(np.int64)],
        "store_id": ds.stores["store_id"].to_numpy()[d["store_code"].astype(np.int64)],
        "sku_id": ds.skus["sku_id"].to_numpy()[d["sku_code"].astype(np.int64)],
    })
    from app.services.synth import DAILY_SPECS

    # business order (stock flow, then till behaviour) rather than the column store's alphabetical file order
    order = [k for k in DAILY_SPECS if k in d] + sorted(k for k in d if k not in DAILY_SPECS)
    for k in order:
        if k not in ("date_idx", "store_code", "sku_code"):
            out[k] = d[k]
    return out


def export(ds_id: str, ctx: jobs.JobContext) -> dict[str, Any]:
    ds = storage.load_dataset(ds_id)
    out = storage.export_path(ds_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".zip.tmp")
    n = ds.meta.n_rows
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=config.EXPORT_COMPRESSLEVEL) as zf:
            ctx.step("daily", f"Writing {n:,} daily rows")
            with zf.open("daily.csv", "w", force_zip64=True) as raw:
                fh = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                for i, a in enumerate(range(0, n, config.CSV_WRITE_CHUNK_ROWS)):
                    ctx.check_cancelled()
                    b = min(n, a + config.CSV_WRITE_CHUNK_ROWS)
                    _daily_frame(ds, a, b).to_csv(fh, index=False, header=(i == 0))
                    ctx.progress(90 * b / n)
                fh.flush()
                fh.detach()
            ctx.step("tables", "Writing stores, SKUs, flags and answer key")
            zf.writestr("stores.csv", ds.stores.to_csv(index=False))
            zf.writestr("skus.csv", ds.skus.to_csv(index=False))
            lp = ds.lp_flags.drop(columns=[c for c in ("date_idx", "store_code", "sku_code") if c in ds.lp_flags])
            zf.writestr("lp_flags.csv", lp.to_csv(index=False))
            if ds.truth:
                tt = np.asarray(ds.truth["truth_type"])
                rows = np.flatnonzero(tt > 0)
                ak = pd.DataFrame({
                    "date": ds.dates[np.asarray(ds.daily["date_idx"])[rows].astype(np.int64)],
                    "store_id": ds.stores["store_id"].to_numpy()[np.asarray(ds.daily["store_code"])[rows].astype(np.int64)],
                    "sku_id": ds.skus["sku_id"].to_numpy()[np.asarray(ds.daily["sku_code"])[rows].astype(np.int64)],
                    "truth_type": np.array(config.ANOMALY_TYPES)[tt[rows]],
                    "truth_incident": np.asarray(ds.truth["truth_incident"])[rows],
                    "truth_loss_units": np.asarray(ds.truth["truth_loss_units"])[rows],
                })
                zf.writestr("answer_key.csv", ak.to_csv(index=False))
            zf.writestr("metadata.json", json.dumps({
                "format": FORMAT, "version": 1, "name": ds.meta.name, "created_at": ds.meta.created_at, "kind": ds.meta.kind,
                "n_rows": n, "n_stores": ds.meta.n_stores, "n_skus": ds.meta.n_skus, "n_days": ds.meta.n_days,
                "date_start": ds.meta.date_start, "date_end": ds.meta.date_end, "params": ds.meta.params,
                "files": {"daily.csv": "one row per store, SKU and day", "stores.csv": "store details", "skus.csv": "SKU details incl. category and unit cost", "lp_flags.csv": "past loss-prevention flags (partial, noisy)", "answer_key.csv": "synthetic only: the injected anomalies (never used as a model input)"},
            }, indent=1))
        os.replace(tmp, out)
    except BaseException:
        storage.safe_unlink(tmp)
        raise
    return {"dataset_id": ds_id, "size_bytes": storage.file_size(out)}


def start_export_job(ds_id: str) -> Job:
    meta = storage.get_dataset_meta(ds_id)
    if meta is None:
        raise LookupError("Dataset not found.")
    return jobs.submit(
        "export", f"Export {meta.name}", lambda ctx: export(ds_id, ctx), params={"dataset_id": ds_id},
        steps=[("daily", "Writing daily rows"), ("tables", "Writing tables")], estimate_seconds=round(meta.n_rows / 1e6 * config.TIMING["export_s_per_1m"] + 3, 1),
    )
