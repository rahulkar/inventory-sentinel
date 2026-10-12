"""Dataset endpoints: generate, import, preview, download, export, delete."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app import config
from app.routers.common import stream_upload
from app.schemas import ConfigureRequest, DatasetMeta, ExportStatus, GenerateRequest, Job, PreviewResponse
from app.services import datasets, exporter, ingest, jobs, storage

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetMeta])
def list_datasets() -> list[DatasetMeta]:
    return storage.list_datasets()


@router.get("/{ds_id}", response_model=DatasetMeta)
def get_dataset(ds_id: str) -> DatasetMeta:
    meta = storage.get_dataset_meta(ds_id)
    if meta is None:
        raise HTTPException(404, "Dataset not found.")
    return meta


@router.post("/generate", response_model=Job, status_code=202)
def generate(req: GenerateRequest) -> Job:
    n = req.n_stores * req.n_skus * req.n_days
    if n < config.MIN_ROWS:
        raise HTTPException(400, f"{n:,} rows is below the minimum of {config.MIN_ROWS:,}. Add stores, SKUs or days.")
    if n > config.MAX_ROWS:
        raise HTTPException(400, f"{n:,} rows is above the maximum of {config.MAX_ROWS:,}.")
    config.ensure_dirs()
    ds_id = storage.new_id("ds")

    def run(ctx: jobs.JobContext) -> dict:
        try:
            ctx.step("simulate", "Simulating stores, SKUs and days")
            last = {"step": "simulate"}

            def prog(f: float, msg: str) -> None:
                if f >= 0.45 and last["step"] == "simulate":
                    ctx.step("features", "Engineering features")
                    last["step"] = "features"
                if f >= 0.95 and last["step"] == "features":
                    ctx.step("summary", "Summarising and saving")
                    last["step"] = "summary"
                ctx.progress(f * 100, msg)

            meta = datasets.generate(req, ds_id, prog, ctx.check_cancelled)
        except BaseException:
            storage.safe_rmtree(storage.dataset_dir(ds_id))
            raise
        return {"dataset_id": meta.id, "n_rows": meta.n_rows}

    est = n / 1e6 * config.TIMING["generate_s_per_1m"] + 3
    return jobs.submit(
        "generate", f"Generate {req.n_stores} stores x {req.n_skus} SKUs x {req.n_days} days ({n:,} rows)", run, params=req.model_dump(),
        steps=[("simulate", "Simulating stores, SKUs and days"), ("features", "Engineering features"), ("summary", "Summarising and saving")], estimate_seconds=round(est, 1),
    )


def _import_job(ds_id: str, src, is_zip: bool, name: str | None, override: dict[str, str] | None, title: str, size: int) -> Job:
    def run(ctx: jobs.JobContext) -> dict:
        ctx.step("read", "Reading and mapping columns")
        last = {"s": "read"}

        def prog(f: float, msg: str) -> None:
            if f >= 0.5 and last["s"] == "read":
                ctx.step("features", "Engineering features")
                last["s"] = "features"
            ctx.progress(f * 100, msg)

        try:
            meta = ingest.process(ds_id, src, is_zip, name, override, prog, ctx.check_cancelled)
        except BaseException:
            if src is not None:
                storage.safe_rmtree(storage.dataset_dir(ds_id))
            raise
        for w in meta.warnings:
            ctx.warn(w)
        return {"dataset_id": meta.id, "n_rows": meta.n_rows}

    return jobs.submit("upload", title, run, params={"dataset_id": ds_id, "bytes": size}, steps=[("read", "Reading and mapping columns"), ("features", "Engineering features")], estimate_seconds=round(size / 1e6 * config.TIMING["upload_s_per_mb"] + 10, 1))


@router.post("/upload", response_model=Job, status_code=202)
async def upload(file: UploadFile = File(...), name: str | None = Form(None), column_map: str | None = Form(None)) -> Job:
    config.ensure_dirs()
    ds_id = storage.new_id("ds")
    d = storage.dataset_dir(ds_id)
    d.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "upload"
    dest = d / ("upload.zip" if filename.lower().endswith(".zip") else "upload.csv")
    size, is_zip = await stream_upload(file, dest)
    override = None
    if column_map:
        import json

        try:
            override = json.loads(column_map)
        except ValueError as exc:
            raise HTTPException(400, f"column_map is not valid JSON: {exc}") from exc
    return _import_job(ds_id, dest, is_zip, (name or "").strip() or None, override, f"Import {filename}", size)


@router.post("/{ds_id}/configure", response_model=Job, status_code=202)
def configure(ds_id: str, req: ConfigureRequest) -> Job:
    meta = storage.get_dataset_meta(ds_id)
    if meta is None:
        raise HTTPException(404, "Dataset not found.")
    if meta.kind != "upload" or not (storage.dataset_dir(ds_id) / "raw").exists():
        raise HTTPException(400, "Only imported datasets keep their raw files for re-mapping.")
    return _import_job(ds_id, None, False, req.name or meta.name, req.column_map, f"Re-process {meta.name}", 0)


@router.get("/{ds_id}/preview", response_model=PreviewResponse)
def preview(ds_id: str, table: str = "daily", rows: int = 25, offset: int = 0, answer_key: bool = False) -> PreviewResponse:
    try:
        ds = storage.load_dataset(ds_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    rows = max(1, min(rows, config.PREVIEW_ROWS_MAX))
    if table == "daily":
        a = max(0, min(offset, ds.meta.n_rows - 1))
        df = exporter._daily_frame(ds, a, min(ds.meta.n_rows, a + rows))
        if answer_key and ds.truth:
            df["truth_type"] = np.array(config.ANOMALY_TYPES)[np.asarray(ds.truth["truth_type"][a : a + len(df)])]
        total = ds.meta.n_rows
    elif table in ("stores", "skus", "lp_flags"):
        full = {"stores": ds.stores, "skus": ds.skus, "lp_flags": ds.lp_flags.drop(columns=[c for c in ("date_idx", "store_code", "sku_code") if c in ds.lp_flags])}[table]
        df = full.iloc[offset : offset + rows]
        total = len(full)
    elif table == "answer_key" and ds.truth:
        tt = np.asarray(ds.truth["truth_type"])
        idx = np.flatnonzero(tt > 0)[offset : offset + rows]
        df = exporter._daily_frame(ds, 0, 0)
        df = pd.DataFrame({"date": ds.dates[np.asarray(ds.daily["date_idx"])[idx].astype(int)], "store_id": ds.stores["store_id"].to_numpy()[np.asarray(ds.daily["store_code"])[idx].astype(int)], "sku_id": ds.skus["sku_id"].to_numpy()[np.asarray(ds.daily["sku_code"])[idx].astype(int)], "truth_type": np.array(config.ANOMALY_TYPES)[tt[idx]], "truth_incident": np.asarray(ds.truth["truth_incident"])[idx]})
        total = int((tt > 0).sum())
    else:
        raise HTTPException(400, "table must be daily, stores, skus, lp_flags or answer_key")
    df = df.astype(object).where(pd.notna(df), None)
    return PreviewResponse(table=table, columns=[str(c) for c in df.columns], rows=[{str(k): (v.item() if hasattr(v, "item") else v) for k, v in r.items()} for r in df.to_dict("records")], total_rows=int(total))


@router.get("/{ds_id}/download")
def download(ds_id: str, table: str = "stores") -> StreamingResponse:
    try:
        ds = storage.load_dataset(ds_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    frames = {"stores": ds.stores, "skus": ds.skus, "lp_flags": ds.lp_flags}
    if table not in frames:
        raise HTTPException(400, "Download stores, skus or lp_flags here; export the dataset for the daily table.")
    buf = io.StringIO()
    frames[table].to_csv(buf, index=False)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{storage.safe_name(ds.meta.name)}_{table}.csv"'})


@router.post("/{ds_id}/export", response_model=Job, status_code=202)
def export(ds_id: str) -> Job:
    try:
        return exporter.start_export_job(ds_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{ds_id}/export", response_model=ExportStatus)
def export_status(ds_id: str) -> ExportStatus:
    return storage.export_status(ds_id)


@router.get("/{ds_id}/export/download")
def export_download(ds_id: str) -> FileResponse:
    meta = storage.get_dataset_meta(ds_id)
    p = storage.export_path(ds_id)
    if meta is None or not p.exists():
        raise HTTPException(404, "Export not built yet.")
    return FileResponse(p, media_type="application/zip", filename=f"{storage.safe_name(meta.name)}.zip")


@router.delete("/{ds_id}")
def delete(ds_id: str) -> dict[str, bool]:
    if jobs.is_busy():
        busy = [j for j in jobs.list_jobs(active_only=True) if j.params.get("dataset_id") == ds_id]
        if busy:
            raise HTTPException(409, "A job is using this dataset; wait for it or cancel it first.")
    if not storage.delete_dataset(ds_id):
        raise HTTPException(404, "Dataset not found.")
    return {"deleted": True}
