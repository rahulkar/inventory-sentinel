"""Models: available methods, training, registry, experiments, export, retrain with feedback."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas import Experiment, Job, ModelMeta, ModelSpecOut, ModelSummary, OnnxStatus, Overview, RetrainRequest, TrainJob, TrainRequest
from app.services import jobs, model_export, registry, reranker, storage, training

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models/available", response_model=list[ModelSpecOut])
def available() -> list[ModelSpecOut]:
    return registry.all_specs()


@router.post("/train", response_model=Job, status_code=202)
def train(req: TrainRequest) -> Job:
    try:
        return training.start_job(req)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/train/{job_id}", response_model=TrainJob)
def train_status(job_id: str) -> TrainJob:
    tj = training.get_job(job_id)
    if tj is None:
        raise HTTPException(404, "Training job not found.")
    return tj


@router.get("/models", response_model=list[ModelSummary])
def models() -> list[ModelSummary]:
    return storage.list_models()


@router.get("/models/active", response_model=ModelMeta | None)
def active_model() -> ModelMeta | None:
    mid = storage.get_active_model_id()
    return storage.get_model(mid) if mid else None


@router.get("/models/{model_id}", response_model=ModelMeta)
def model(model_id: str) -> ModelMeta:
    m = storage.get_model(model_id)
    if m is None:
        raise HTTPException(404, "Model not found.")
    return m


@router.post("/models/{model_id}/activate", response_model=ModelSummary)
def activate(model_id: str) -> ModelSummary:
    if storage.get_model_summary(model_id) is None:
        raise HTTPException(404, "Model not found.")
    storage.set_active_model(model_id)
    return storage.get_model_summary(model_id)  # type: ignore[return-value]


@router.delete("/models/{model_id}")
def delete(model_id: str) -> dict[str, bool]:
    if not storage.delete_model(model_id):
        raise HTTPException(404, "Model not found.")
    return {"deleted": True}


@router.post("/models/{model_id}/retrain-feedback", response_model=Job, status_code=202)
def retrain(model_id: str, req: RetrainRequest) -> Job:
    try:
        return reranker.start_job(model_id, req)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/experiments", response_model=list[Experiment])
def experiments() -> list[Experiment]:
    return training.experiments()


@router.get("/models/{model_id}/export")
def export_bundle(model_id: str) -> FileResponse:
    try:
        path, filename = model_export.build_bundle(model_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="application/zip", filename=filename)


@router.get("/models/{model_id}/onnx", response_model=OnnxStatus)
def onnx_status(model_id: str) -> OnnxStatus:
    try:
        return model_export.onnx_status(model_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/models/{model_id}/export/onnx", response_model=Job, status_code=202)
def onnx_export(model_id: str) -> Job:
    try:
        return model_export.start_onnx_job(model_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/models/{model_id}/onnx/download")
def onnx_download(model_id: str) -> FileResponse:
    m = storage.get_model(model_id)
    p = storage.model_paths(model_id)["onnx"]
    if m is None or not p.exists():
        raise HTTPException(404, "ONNX file not built yet.")
    return FileResponse(p, media_type="application/octet-stream", filename=f"inventory_sentinel_{m.key}_{model_id}.onnx")


@router.get("/overview", response_model=Overview)
def overview() -> Overview:
    from app.services import detection

    models = storage.list_models()
    active = next((m for m in models if m.is_active), None)
    scored = [m for m in models if m.metrics.average_precision is not None]
    best = max(scored, key=lambda m: m.metrics.average_precision or 0) if scored else None
    runs = storage.list_runs()
    latest = None
    top = []
    if runs:
        try:
            rd = storage.load_run(runs[0].run_id)
            latest = rd.run
            # the alerts the investigation planner would work first: varied and actionable (most-unusual-first is dominated by typing errors)
            from app.services import planner

            top = [detection.get_alert(runs[0].run_id, a) for a in planner.top_alert_ids(runs[0].run_id, 5)] or detection.list_alerts(runs[0].run_id, limit=5).alerts
        except LookupError:
            pass
    return Overview(n_datasets=len(storage.list_datasets()), n_models=len(models), n_runs=len(runs), active_model=active, best_model=best, latest_run=latest, top_alerts=top, recent_jobs=jobs.list_jobs(limit=8))
