"""Services-level smoke: generate -> train 4 -> detect -> plan -> simulate triage -> retrain -> detect -> ONNX -> bundle predict.py."""
import os, sys, time, json, tempfile, zipfile, subprocess
os.environ.setdefault("SENTINEL_MIN_ROWS", "50000")
import numpy as np
from app import config
config.DATA_DIR = config.ROOT / "data_smoke"
for k in ("DATASETS_DIR", "MODELS_DIR", "RUNS_DIR", "TRIAGE_DIR", "EXPORTS_DIR"):
    setattr(config, k, config.DATA_DIR / getattr(config, k).name)
config.REGISTRY_PATH = config.DATA_DIR / "registry.json"
config.ensure_dirs()
from app.schemas import GenerateRequest, TrainRequest, ModelSelection, DetectRequest, PlanRequest, SimulateTriageRequest, RetrainRequest
from app.services import jobs, storage, training, detection, planner, triage, reranker, model_export, exporter

def wait(job, label):
    t = time.time()
    while True:
        j = jobs.get(job.job_id)
        if j.status in ("done", "failed", "cancelled"):
            break
        time.sleep(0.3)
    print(f"{label:28s} {j.status} in {time.time()-t:6.1f}s {('ERROR ' + str(j.error)) if j.error else ''} {j.warnings[:2] if j.warnings else ''}", flush=True)
    assert j.status == "done", j.error
    return j.result

ns, nk, nd = (int(x) for x in (sys.argv[1:4] if len(sys.argv) > 3 else (40, 125, 100)))
from app.routers.datasets import generate
res = wait(generate(GenerateRequest(n_stores=ns, n_skus=nk, n_days=nd)), f"generate {ns*nk*nd:,}")
ds_id = res["dataset_id"]; meta = storage.get_dataset_meta(ds_id)
print("  dataset", meta.n_rows, meta.n_incidents, "incidents", meta.n_lp_flags, "lp flags; test from", meta.test_from_date, "size MB", round(meta.size_bytes/1e6, 1))
res = wait(training.start_job(TrainRequest(dataset_id=ds_id, models=[ModelSelection(key=k) for k in ["zscore", "iforest", "autoencoder", "lof"]])), "train 4 methods")
for mid in res["model_ids"]:
    m = storage.get_model(mid); mm = m.metrics
    print(f"  {m.key:12s} AP {mm.average_precision} p@1k {mm.precision_at_k} incRec {mm.incident_recall} valCap {mm.value_captured_pct} lpRec {mm.lp_recall} engine {m.engine} onnx {m.onnx_ok} fit {mm.fit_seconds}s score/1M {mm.score_seconds_per_1m}s")
best = res["best_model_id"]
res = wait(detection.start_job(DetectRequest(dataset_id=ds_id)), "detect (best)")
run_id = res["run_id"]; rd = storage.load_run(run_id)
print("  run", rd.run.kpis.model_dump(exclude={"by_type"}), "\n  eval", rd.run.evaluation)
page = detection.list_alerts(run_id, limit=3)
for a in page.alerts: print("  ", a.alert_id, a.severity, a.store_id, a.sku_id, a.likely_type, round(a.value_at_risk_gbp,1), a.p_true, a.reasons[:2])
s = detection.series(run_id, page.alerts[0].store_id, page.alerts[0].sku_id, answer_key=True)
print("  series points", len(s.points), "flagged", sum(p.severity > 0 for p in s.points), "reasons days", len(s.flagged_reasons))
print("  search S001:", [ (m.store_id, m.sku_id, m.n_alerts) for m in detection.search(run_id, "S001")[:3]])
p = planner.plan(PlanRequest(run_id=run_id))
print(f"  plan: {p.n_selected}/{p.n_candidates} alerts, {p.hours_used}h, EV £{p.expected_recovered:,.0f}, cost £{p.cost:,.0f}, ROI {p.roi}, naive £{p.naive_expected:,.0f}, breakeven {p.breakeven_hours}")
print("  worklist csv lines", len(planner.worklist_csv(PlanRequest(run_id=run_id)).splitlines()), "zip bytes", len(planner.worklist_zip(PlanRequest(run_id=run_id))))
print("  simulate", triage.simulate(SimulateTriageRequest(run_id=run_id, days=5, per_day=25)))
summ = triage.summary(ds_id, run_id); print("  triage", summ.reviewed, summ.precision, summ.can_retrain, summ.retrain_reason)
print("  recalibrate", {k: v for k, v in detection.recalibrate(run_id).items() if k != "calibration"})
res = wait(reranker.start_job(best, RetrainRequest()), "retrain with feedback")
print("  feedback eval", json.dumps(res["feedback_eval"]["base"]), "->", json.dumps(res["feedback_eval"]["reranker"]))
res2 = wait(detection.start_job(DetectRequest(dataset_id=ds_id)), "detect (re-ranker)")
for mid in [m.model_id for m in storage.list_models() if m.key in ("iforest", "autoencoder", "lof", "zscore")]:
    m = storage.get_model(mid)
    r = wait(model_export.start_onnx_job(mid), f"onnx {m.key}")
    print(f"  {m.key}: spearman {r['spearman']} top1 {r['top1_overlap']} maxdiff {r['max_abs_diff']:.2e}")
path, fname = model_export.build_bundle(best)
wait(exporter.start_export_job(ds_id), "export dataset ZIP")
tmp = tempfile.mkdtemp()
with zipfile.ZipFile(path) as z: z.extractall(tmp)
with zipfile.ZipFile(storage.export_path(ds_id)) as z:
    z.extract("skus.csv", tmp)
    with z.open("daily.csv") as fh:
        import pandas as pd
        pd.read_csv(fh, nrows=20000).to_csv(os.path.join(tmp, "daily.csv"), index=False)
for flag in ([], ["--onnx"]):
    out = subprocess.run([sys.executable, "predict.py", "daily.csv", "scored.csv", "--skus", "skus.csv"] + flag, cwd=tmp, capture_output=True, text=True)
    print("  predict.py", flag, out.returncode, (out.stdout or out.stderr).strip()[-200:])
print("ALL SERVICE CHECKS PASSED")
