"""Services-level smoke, end to end against a live demo vendor over MCP.

    PYTHONPATH=backend python backend/tests/service_smoke.py [stores skus history_days]

Starts vendor_mock on a free port (small estate, temp data dir) -> connector -> sync -> train 4 -> detect -> SOP ->
vendor task (proposal) -> store closes it in the back-office -> outcome read back as feedback -> plan -> simulate
triage -> retrain -> advance the vendor clock -> incremental sync + retention -> schedules (timer + retrain) -> ONNX ->
bundle predict.py. Uses data_smoke/ (wiped first; SENTINEL_SMOKE_DIR overrides).
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("SENTINEL_SMOKE_DIR") or ROOT / "data_smoke")  # wiped first; point elsewhere when this disk is tight
shutil.rmtree(DATA, ignore_errors=True)
os.environ["SENTINEL_DATA_DIR"] = str(DATA)

from app import config  # noqa: E402

config.ensure_dirs()
from app.assistant import proposals  # noqa: E402
from app.schemas import ConnectorIn, DetectRequest, ModelSelection, PlanRequest, RetrainRequest, ScheduleIn, SimulateTriageRequest, TrainRequest  # noqa: E402
from app.services import connectors, detection, exporter, jobs, model_export, planner, reranker, scheduler, sops, storage, sync, training, triage, vendor_tasks  # noqa: E402

TOKEN = "smoke-token"


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


def check(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + ("" if ok else f" -> {str(detail)[:400]}"), flush=True)
    assert ok, name


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(method, url, data=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data is not None else None, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode()


ns, nk, nh = (int(x) for x in (sys.argv[1:4] if len(sys.argv) > 3 else (12, 120, 130)))
port = free_port()
VBASE = f"http://127.0.0.1:{port}"
vendor_dir = tempfile.mkdtemp(prefix="vendor_smoke_")
vendor = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "vendor_mock.app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=ROOT,
    env=dict(os.environ, VENDOR_MOCK_DATA_DIR=vendor_dir, VENDOR_MOCK_STORES=str(ns), VENDOR_MOCK_SKUS=str(nk), VENDOR_MOCK_HISTORY_DAYS=str(nh),
             VENDOR_MOCK_FUTURE_DAYS="15", VENDOR_MOCK_TOKEN=TOKEN, VENDOR_MOCK_PUBLIC_URL=VBASE, PYTHONUTF8="1"),
)
try:
    t0 = time.time()
    while True:
        try:
            if json.loads(http("GET", VBASE + "/health")[1]).get("data") == "ready":
                break
        except OSError:
            pass
        assert time.time() - t0 < 180, "vendor mock did not start"
        time.sleep(0.5)
    print(f"vendor mock ready on {VBASE} in {time.time()-t0:.1f}s ({ns} stores x {nk} SKUs x {nh} days of history)")

    # ---- connector + first sync
    bad = connectors.test(connectors.Connector(id="conn_00000000", created_at="", name="no token", url=VBASE + "/mcp/"))
    check("wrong credentials are reported", not bad.ok and "token" in (bad.error or "").lower(), bad)
    c = connectors.create(ConnectorIn(name="Smoke vendor", url=VBASE + "/mcp/", token=TOKEN))
    t = connectors.refresh_capabilities(c.id)
    check("connector test", t.ok and t.capabilities["counts"]["stores"] == ns, t)
    check("token masked in output", connectors.to_out(connectors.get(c.id)).token != TOKEN)
    res = wait(sync.start_job(c.id), "sync (first, full window)")
    ds_id = res["dataset_id"]
    meta = storage.get_dataset_meta(ds_id)
    print("  dataset", meta.n_rows, "rows", meta.n_days, "days", meta.date_start, "->", meta.date_end, meta.n_incidents, "incidents", meta.n_lp_flags, "lp flags; test from", meta.test_from_date)
    check("snapshot is a connector dataset with the demo answer key", meta.kind == "connector" and meta.has_truth and meta.params["connector_id"] == c.id, meta.params)
    check("snapshot covers the window", meta.n_days == min(config.SYNC_WINDOW_DAYS, nh) and meta.n_rows == ns * nk * meta.n_days, (meta.n_days, meta.n_rows))
    pos = connectors.stock_position(c.id, "S001", "K00001", 3)
    check("live stock lookup", pos["on_hand"] is not None and len(pos["last_days"]) == 3, pos)

    # ---- train / detect (unchanged pipeline, now on vendor data)
    res = wait(training.start_job(TrainRequest(dataset_id=ds_id, models=[ModelSelection(key=k) for k in ["zscore", "iforest", "autoencoder", "lof"]], train_sample_size=60_000)), "train 4 methods")
    for mid in res["model_ids"]:
        m = storage.get_model(mid)
        mm = m.metrics
        print(f"  {m.key:12s} AP {mm.average_precision} p@1k {mm.precision_at_k} incRec {mm.incident_recall} valCap {mm.value_captured_pct} engine {m.engine} onnx {m.onnx_ok}")
    best = res["best_model_id"]
    res = wait(detection.start_job(DetectRequest(dataset_id=ds_id)), "detect (best)")
    run_id = res["run_id"]
    rd = storage.load_run(run_id)
    print("  run", rd.run.kpis.model_dump(exclude={"by_type"}), "\n  eval", rd.run.evaluation)
    page = detection.list_alerts(run_id, limit=3)
    for a in page.alerts:
        print("  ", a.alert_id, a.severity, a.store_id, a.sku_id, a.likely_type, round(a.value_at_risk_gbp, 1), a.p_true)
    top = page.alerts[0]

    # ---- SOP + vendor task write-back
    asop = sops.for_alert(run_id, top.alert_id)
    print("  SOP", asop.sop.id, "escalation", asop.escalation.level if asop.escalation else None, "steps", [s.id for s in asop.steps])
    check("SOP for the alert", asop.sop.id == sops.sop_id_for_type(top.likely_type) and asop.escalation is not None and asop.can_raise_tasks, asop.sop.id)
    p = proposals.create("smoke", "vendor_task", {"run_id": run_id, "tasks": [{"alert_id": top.alert_id}]})
    print("  proposal:", p.title, "|", p.summary[:160])
    out = proposals.execute(p.proposal_id)
    check("vendor task proposal executed", out["proposal"].status == "confirmed" and len(out["result"]["created"]) == 1, out)
    task = out["result"]["created"][0]
    again = vendor_tasks.create([vendor_tasks.VendorTaskDraft(run_id=run_id, alert_id=top.alert_id, type=task["type"])], connector_id=c.id)
    check("raising the same task again is idempotent", not again["created"] and len(again["existing"]) == 1, again)
    remote = connectors.call(connectors.get(c.id), "get_task", {"task_id": task["task_id"]})
    check("task visible in the vendor back-office", remote["source_alert_id"] == top.alert_id and remote["status"] == "open", remote)
    http("POST", f"{VBASE}/tasks/{task['task_id']}", {"status": "done", "outcome": "no_issue", "note": "stock found in stockroom"})
    n = vendor_tasks.refresh(connectors.get(c.id))
    fb = [r for r in triage.all_records(ds_id) if r.get("source") == "vendor_task"]
    check("closed task read back as team feedback", n >= 1 and len(fb) == 1 and fb[0]["outcome"] == "false_alarm", (n, fb))

    # ---- planner, simulated triage, feedback re-ranker
    pl = planner.plan(PlanRequest(run_id=run_id))
    print(f"  plan: {pl.n_selected}/{pl.n_candidates} alerts, {pl.hours_used}h, EV £{pl.expected_recovered:,.0f}, ROI {pl.roi}")
    print("  simulate", triage.simulate(SimulateTriageRequest(run_id=run_id, days=5, per_day=25)))
    summ = triage.summary(ds_id, run_id)
    print("  triage", summ.reviewed, summ.precision, summ.can_retrain, summ.retrain_reason)
    res = wait(reranker.start_job(best, RetrainRequest()), "retrain with feedback")
    print("  feedback eval", json.dumps(res["feedback_eval"]["base"]), "->", json.dumps(res["feedback_eval"]["reranker"]))
    storage.set_active_model(best)

    # ---- next business day: incremental sync, feedback survives, retention
    http("POST", VBASE + "/api/advance?days=1")
    res2 = wait(sync.start_job(c.id), "sync (incremental)")
    meta2 = storage.get_dataset_meta(res2["dataset_id"])
    check("incremental sync pulls only recent days", res2["days_pulled"] == config.SYNC_RESYNC_DAYS + 1, res2)
    check("new snapshot moved forward one day", meta2.date_end > meta.date_end and meta2.n_days == meta.n_days, (meta.date_end, meta2.date_end))
    check("team feedback carries over to the new snapshot", triage.summary(meta2.id, None).reviewed == summ.reviewed, triage.summary(meta2.id, None).reviewed)
    for _ in range(config.CONNECTOR_RETENTION):
        http("POST", VBASE + "/api/advance?days=1")
        wait(sync.start_job(c.id), "sync (retention)")
    snaps = connectors.connector_datasets(c.id)
    check("retention keeps the newest snapshots plus the model's training data", len(snaps) <= config.CONNECTOR_RETENTION + 1 and storage.get_dataset_meta(ds_id) is not None, [d.id for d in snaps])

    # ---- schedules
    s1 = scheduler.create(ScheduleIn(name="Smoke daily", connector_id=c.id, pipeline={"model_policy": "active", "auto_tasks": {"enabled": True, "severities": ["critical", "high", "medium"], "max_tasks": 3}}))
    print("  schedule:", scheduler.describe(s1), "| next", s1.next_run_at)
    due = scheduler._parse(s1.next_run_at) + timedelta(seconds=5)
    started = scheduler.tick(due)
    check("timer starts the due schedule", len(started) == 1 and started[0].trigger == "timer" and started[0].job_id, started)
    wait(jobs.get(started[0].job_id), "scheduled pipeline (active)")
    r1 = scheduler.get_run(started[0].run_id)
    print("  run:", r1.status, "alerts", r1.alerts, "new", r1.new_alerts, "critical", r1.new_critical, "proposal", r1.proposal_id, r1.warnings[:1])
    check("scheduled run synced and detected", r1.status == "done" and r1.detection_run_id and r1.dataset_id, r1)
    pend = proposals.list_pending(source="scheduler")
    check("vendor tasks from the scheduled run wait for approval", (r1.proposal_id is None and not r1.new_alerts) or any(p.proposal_id == r1.proposal_id for p in pend), (r1.proposal_id, [p.proposal_id for p in pend]))
    check("next run moved on", scheduler._parse(scheduler.get(s1.id).next_run_at) > due)
    late = scheduler.tick(scheduler._parse(scheduler.get(s1.id).next_run_at) + timedelta(hours=5))
    check("a run missed while down becomes a catch-up", late and late[0].trigger == "catch_up", late)
    wait(jobs.get(late[0].job_id), "scheduled pipeline (catch-up)")
    s2 = scheduler.create(ScheduleIn(name="Smoke retrain", connector_id=c.id, frequency={"kind": "interval", "every_hours": 6}, pipeline={"sync": False, "model_policy": "retrain", "train": {"models": [{"key": "iforest"}], "train_sample_size": 30_000}}))
    run, job = scheduler.run_now(s2.id)
    wait(job, "scheduled pipeline (retrain)")
    r2 = scheduler.get_run(run.run_id)
    check("retrain schedule trains its own model without swapping the one in use", r2.status == "done" and r2.retrained and r2.model_id != best and storage.get_active_model_id() == best, r2)
    pr = proposals.create("smoke", "create_schedule", {"at": "05:30", "days": ["mon", "wed", "fri"], "models": ["lof"], "auto_tasks": True})
    print("  chat proposal:", pr.title, "|", pr.summary)
    check("schedule proposal from chat-style shortcuts", pr.params["schedule"]["frequency"]["days"] == [0, 2, 4] and pr.params["schedule"]["pipeline"]["model_policy"] == "retrain", pr.params)

    # ---- ONNX + bundle (unchanged)
    for mid in [m.model_id for m in storage.list_models() if m.key in ("iforest", "autoencoder", "lof", "zscore")][:4]:
        m = storage.get_model(mid)
        r = wait(model_export.start_onnx_job(mid), f"onnx {m.key}")
        print(f"  {m.key}: spearman {r['spearman']} top1 {r['top1_overlap']} maxdiff {r['max_abs_diff']:.2e}")
    path, fname = model_export.build_bundle(best)
    wait(exporter.start_export_job(ds_id), "export dataset ZIP")
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(path) as z:
        z.extractall(tmp)
    with zipfile.ZipFile(storage.export_path(ds_id)) as z:
        z.extract("skus.csv", tmp)
        with z.open("daily.csv") as fh:
            import pandas as pd

            pd.read_csv(fh, nrows=20000).to_csv(os.path.join(tmp, "daily.csv"), index=False)
    for flag in ([], ["--onnx"]):
        out = subprocess.run([sys.executable, "predict.py", "daily.csv", "scored.csv", "--skus", "skus.csv"] + flag, cwd=tmp, capture_output=True, text=True)
        print("  predict.py", flag, out.returncode, (out.stdout or out.stderr).strip()[-200:])
        check(f"bundle predict.py {flag}", out.returncode == 0, out.stderr[-300:])
    print("ALL SERVICE CHECKS PASSED")
finally:
    vendor.terminate()
    try:
        vendor.wait(timeout=10)
    except subprocess.TimeoutExpired:
        vendor.kill()
