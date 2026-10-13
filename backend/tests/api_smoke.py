"""End-to-end API check against a running server and a vendor connector.

    python backend/tests/api_smoke.py [--base http://127.0.0.1:8000] [--vendor http://127.0.0.1:8020/mcp/] [--vendor-token T] [--keep]

Registers the vendor (the demo back-office by default) as a connector unless it already is, syncs it, then trains,
detects, plans, exercises SOPs, vendor tasks and schedules, exports and re-imports. The data size is whatever the vendor
holds (start vendor_mock with VENDOR_MOCK_STORES / _SKUS / _HISTORY_DAYS for a quick run). --keep leaves the data in place.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:8000")
ap.add_argument("--vendor", default="http://127.0.0.1:8020/mcp/")
ap.add_argument("--vendor-token", default=None)
ap.add_argument("--keep", action="store_true")
args = ap.parse_args()
B = args.base
TIMES: list[tuple[str, float]] = []


def call(method: str, path: str, body=None, raw: bool = False, timeout: int = 600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload
            return r.status, (json.loads(payload) if "json" in r.headers.get("Content-Type", "") else payload)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def check(label: str, cond: bool, detail="") -> None:
    print(("PASS" if cond else "FAIL"), label, "" if cond else str(detail)[:600], flush=True)
    if not cond:
        sys.exit(1)


def wait_job(job: dict, label: str) -> dict:
    t0 = time.time()
    while True:
        s, j = call("GET", f"/api/jobs/{job['job_id']}")
        if j["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.5)
    el = time.time() - t0
    TIMES.append((label, el))
    check(f"{label} ({el:.1f}s)", j["status"] == "done", j.get("error"))
    return j["result"]


def upload(path: str, filename: str, fields: dict[str, str]) -> tuple[int, dict]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    with open(path, "rb") as fh:
        content = fh.read()
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(B + "/api/datasets/upload", data=b"".join(parts), method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.status, json.loads(r.read())


s, h = call("GET", "/api/health")
check("health", s == 200 and h["status"] == "ok", h)
print("     engines:", h["engines"], "| issues:", len(h["env_issues"]))
s, cfg = call("GET", "/api/config")
check("config", s == 200 and cfg["max_rows"] > 0, cfg)

# ---------------------------------------------------------------- data: vendor connector over MCP
s, conns = call("GET", "/api/connectors")
conn = next((c for c in conns if c["url"].rstrip("/") == args.vendor.rstrip("/")), None) if s == 200 else None
if conn is None:
    s, conn = call("POST", "/api/connectors", {"name": "API smoke vendor", "url": args.vendor, "token": args.vendor_token})
    check("connector created", s == 201 and conn["capabilities"], conn)
s, t = call("POST", f"/api/connectors/{conn['id']}/test")
check("connector test", s == 200 and t["ok"] and t["capabilities"]["status"] == "ready", t)
check("token never returned", not conn["token"] or "•" in conn["token"] or conn["token"].startswith("*"), conn["token"])
s, job = call("POST", f"/api/connectors/{conn['id']}/sync")
check("sync accepted", s == 202, job)
ds_id = wait_job(job, "sync vendor")["dataset_id"]
s, meta = call("GET", f"/api/datasets/{ds_id}")
check("snapshot meta", s == 200 and meta["kind"] == "connector" and meta["n_lp_flags"] > 0, meta)
size = (meta["n_stores"], meta["n_skus"], meta["n_days"])
s, pos = call("GET", f"/api/connectors/{conn['id']}/lookup?store_id=S001&sku_id=K00001&days=3")
check("live stock lookup", s == 200 and pos["on_hand"] is not None, pos)
print(f"     {meta['n_rows']:,} rows, {meta['n_incidents']:,} injected incidents, {meta['n_lp_flags']} LP flags, {meta['size_bytes'] / 1e6:.0f} MB")
for t in ("daily", "stores", "skus", "lp_flags"):
    s, pv = call("GET", f"/api/datasets/{ds_id}/preview?table={t}&rows=5")
    check(f"preview {t}", s == 200 and len(pv["rows"]) > 0, pv)
if meta["has_truth"]:
    s, pv = call("GET", f"/api/datasets/{ds_id}/preview?table=daily&rows=5&answer_key=true")
    check("preview with the demo answer key", "truth_type" in pv["columns"], pv["columns"])

# ---------------------------------------------------------------- train
s, av = call("GET", "/api/models/available")
keys = [m["key"] for m in av if m["available"]]
check("methods available", {"zscore", "iforest", "autoencoder", "lof"} <= set(keys), keys)
s, job = call("POST", "/api/train", {"dataset_id": ds_id, "models": [{"key": k} for k in ["zscore", "iforest", "autoencoder", "lof"]]})
check("train accepted", s == 202, job)
res = wait_job(job, "train 4 methods")
s, tj = call("GET", f"/api/train/{job['job_id']}")
check("train job detail", s == 200 and tj["status"] == "done", tj)
ms = {m["key"]: m for m in call("GET", "/api/models")[1]}
for k in ("zscore", "iforest", "autoencoder", "lof"):
    x = ms[k]["metrics"]
    print(f"     {k:12s} AP {x['average_precision']} p@1k {x['precision_at_k']} incidents {x['incident_recall']} value {x['value_captured_pct']}% engine {ms[k]['engine']}")
best = max((m for m in ms.values() if m["key"] != "zscore"), key=lambda m: m["metrics"]["average_precision"])
check("ML beats the rule of thumb (AP +0.05)", best["metrics"]["average_precision"] >= ms["zscore"]["metrics"]["average_precision"] + 0.05, {k: v["metrics"]["average_precision"] for k, v in ms.items()})
s, active = call("GET", f"/api/models/{res['best_model_id']}")
check("best model active", active["is_active"], active.get("is_active"))
s, ex = call("GET", "/api/experiments")
check("experiments", s == 200 and ex and ex[0]["models"], ex[:1])

# ---------------------------------------------------------------- detect
s, job = call("POST", "/api/detect", {"dataset_id": ds_id})
run_id = wait_job(job, "detect (best model)")["run_id"]
s, run = call("GET", f"/api/runs/{run_id}")
check("run", s == 200 and run["kpis"]["incidents"] > 0, run)
print(f"     {run['kpis']['incidents']:,} alerts, £{run['kpis']['value_at_risk_gbp']:,.0f} at risk; eval {run['evaluation']}")
s, dash = call("GET", f"/api/runs/{run_id}/dashboard")
check("dashboard", s == 200 and dash["trend"] and dash["heatmap"] and dash["top_stores"], list(dash))
s, page = call("GET", f"/api/runs/{run_id}/alerts?limit=5&severity=critical&severity=high")
check("alerts filtered", s == 200 and page["total"] > 0 and all(a["severity"] in ("critical", "high") for a in page["alerts"]), page)
a0 = page["alerts"][0]
s, a = call("GET", f"/api/runs/{run_id}/alerts/{a0['alert_id']}?answer_key=true")
check("alert detail with reasons", s == 200 and a["reasons"] and "truth_type" in a, a)
s, asop = call("GET", f"/api/runs/{run_id}/alerts/{a0['alert_id']}/sop")
check("alert SOP", s == 200 and asop["sop"]["id"] and asop["steps"] and asop["escalation"], asop)
step = next((x for x in asop["steps"] if x["vendor_task"]), None)
if step and asop["can_raise_tasks"]:
    body = {"tasks": [{"run_id": run_id, "alert_id": a0["alert_id"], "type": step["vendor_task"]["type"], "sop_id": asop["sop"]["id"], "sop_step": step["id"]}]}
    s, raised = call("POST", "/api/vendor-tasks", body)
    check("vendor task raised", s == 200 and (raised["created"] or raised["existing"]), raised)
    s, again = call("POST", "/api/vendor-tasks", body)
    check("vendor task idempotent", s == 200 and not again["created"] and again["existing"], again)
s, sops = call("GET", "/api/sops")
check("SOP list", s == 200 and any(x["id"] == "missing-inventory-response" for x in sops), sops)
s, ser = call("GET", f"/api/runs/{run_id}/series?store_id={a0['store_id']}&sku_id={a0['sku_id']}&answer_key=true")
check("series drill-down", s == 200 and len(ser["points"]) == size[2] and ser["alerts"] and ser["flagged_reasons"], {k: ser[k] for k in ("store_id", "sku_id")} if s == 200 else ser)
s, found = call("GET", f"/api/runs/{run_id}/search?q={a0['store_id']}")
check("series search", s == 200 and found, found)
s, csv = call("GET", f"/api/runs/{run_id}/alerts.csv", raw=True)
check("alerts csv", s == 200 and csv.count(b"\n") > 1, csv[:200])

# ---------------------------------------------------------------- schedules
sched_body = {"name": "API smoke", "enabled": False, "connector_id": conn["id"], "timezone": "Europe/London",
              "frequency": {"kind": "weekly", "every_hours": 24, "at": "05:30", "days": [0, 3]},
              "pipeline": {"sync": False, "model_policy": "active", "model_id": None,
                           "train": {"models": [{"key": "iforest", "params": {}}], "train_sample_size": 30000, "alert_rate": 0.008, "activate_retrained": False, "min_interval_days": 0},
                           "auto_tasks": {"enabled": True, "severities": ["critical"], "min_value_gbp": 0, "max_tasks": 2}},
              "catch_up": "once"}
s, pv = call("POST", "/api/schedules/preview", sched_body)
check("schedule preview", s == 200 and len(pv["next_runs"]) == 3 and "05:30" in pv["summary"], pv)
s, sched = call("POST", "/api/schedules", sched_body)
check("schedule created", s == 201 and sched["next_run_at"], sched)
s, out = call("POST", f"/api/schedules/{sched['id']}/run")
check("schedule run now", s == 200 and out["job"], out)
wait_job(out["job"], "scheduled pipeline")
s, sruns = call("GET", f"/api/schedules/{sched['id']}/runs")
check("schedule history", s == 200 and sruns and sruns[0]["status"] == "done" and sruns[0]["detection_run_id"], sruns[:1])
s, st = call("GET", "/api/schedules/status")
check("scheduler status", s == 200 and "running" in st, st)
bad = dict(sched_body, timezone="Mars/Olympus")
s, err = call("POST", "/api/schedules", bad)
check("bad timezone rejected", s == 400, err)

# ---------------------------------------------------------------- planner
s, plan = call("POST", "/api/plan", {"run_id": run_id, "hours": 60})
check("plan", s == 200 and plan["n_selected"] > 0 and plan["expected_recovered"] > 0 and plan["curve"], plan)
print(f"     60h: {plan['n_selected']} alerts, £{plan['expected_recovered']:,.0f} expected, ROI {plan['roi']:.1f}x, naive £{plan['naive_expected']:,.0f}")
s, wl = call("GET", f"/api/plan/{run_id}/worklist.csv?hours=60", raw=True)
check("worklist csv", s == 200 and wl.startswith(b"priority,"), wl[:120])
s, wz = call("GET", f"/api/plan/{run_id}/worklist.zip?hours=60", raw=True)
check("worklist zip", s == 200 and zipfile.ZipFile(io.BytesIO(wz)).namelist(), "")

# ---------------------------------------------------------------- triage and feedback
s, d1 = call("POST", "/api/triage", {"run_id": run_id, "alert_id": a0["alert_id"], "outcome": "confirmed_theft", "note": "smoke"})
check("triage decision", s == 200 and d1["saved"], d1)
s, sim = call("POST", "/api/triage/simulate", {"run_id": run_id, "days": 5, "per_day": 15})
check("simulate triage", s == 200 and sim["reviewed"] > 0, sim)
s, summ = call("GET", f"/api/triage/summary?dataset_id={ds_id}&run_id={run_id}")
check("triage summary", s == 200 and summ["reviewed"] >= sim["reviewed"] and summ["by_day"], summ)
s, rc = call("POST", f"/api/runs/{run_id}/recalibrate")
check("recalibrate from triage", s == 200 and rc["reviewed"] >= 10, rc)
s, page2 = call("GET", f"/api/runs/{run_id}/alerts?status=reviewed&limit=3")
check("reviewed alerts filter", s == 200 and page2["total"] >= 1, page2)
if summ["can_retrain"]:
    s, job = call("POST", f"/api/models/{best['model_id']}/retrain-feedback", {"alpha": 0.4})
    rr = wait_job(job, "retrain with feedback")
    fe = rr["feedback_eval"]
    print("     base", fe["base"], "\n     re-ranker", fe["reranker"])
    check("re-ranker not worse on unreviewed days", (fe["reranker"]["average_precision"] or 0) >= (fe["base"]["average_precision"] or 0) - 0.02, fe)
    s, job = call("POST", "/api/detect", {"dataset_id": ds_id})
    wait_job(job, "detect (re-ranker)")
else:
    print("     (retrain skipped:", summ["retrain_reason"], ")")

# ---------------------------------------------------------------- export: dataset and models
s, job = call("POST", f"/api/datasets/{ds_id}/export")
wait_job(job, "export dataset ZIP")
s, zbytes = call("GET", f"/api/datasets/{ds_id}/export/download", raw=True)
check("download export", s == 200 and len(zbytes) > 1000, len(zbytes) if isinstance(zbytes, bytes) else zbytes)
tmpdir = tempfile.mkdtemp()
zpath = os.path.join(tmpdir, "export.zip")
open(zpath, "wb").write(zbytes)
names = zipfile.ZipFile(zpath).namelist()
check("export contents", {"daily.csv", "stores.csv", "skus.csv", "lp_flags.csv", "answer_key.csv", "metadata.json"} <= set(names), names)
t0 = time.time()
s, job = upload(zpath, "export.zip", {"name": "Re-imported export"})
ds2 = wait_job(job, "re-import the ZIP")["dataset_id"]
s, meta2 = call("GET", f"/api/datasets/{ds2}")
check("re-import keeps rows, flags and answer key", meta2["n_rows"] == meta["n_rows"] and meta2["has_truth"] and meta2["n_lp_flags"] == meta["n_lp_flags"] and meta2["n_incidents"] == meta["n_incidents"], {k: (meta[k], meta2[k]) for k in ("n_rows", "n_lp_flags", "n_incidents")})
for k in ("zscore", "iforest", "autoencoder", "lof"):
    s, job = call("POST", f"/api/models/{ms[k]['model_id']}/export/onnx")
    check(f"onnx {k} accepted", s == 202, job)
    r = wait_job(job, f"onnx {k}")
    check(f"onnx {k} matches", r["spearman"] >= 0.999 and r["top1_overlap"] >= 0.98, r)
s, bundle = call("GET", f"/api/models/{best['model_id']}/export", raw=True)
check("model bundle", s == 200 and bundle[:2] == b"PK", "")
bdir = os.path.join(tmpdir, "bundle")
zipfile.ZipFile(io.BytesIO(bundle)).extractall(bdir)
with zipfile.ZipFile(zpath) as z:
    z.extract("skus.csv", bdir)
    import pandas as pd

    with z.open("daily.csv") as fh:
        pd.read_csv(fh, nrows=size[2] * 50).to_csv(os.path.join(bdir, "daily.csv"), index=False)
for extra in ([], ["--onnx"]):
    out = subprocess.run([sys.executable, "predict.py", "daily.csv", "scored.csv", "--skus", "skus.csv", *extra], cwd=bdir, capture_output=True, text=True, timeout=300)
    check(f"bundle predict.py {' '.join(extra) or '(joblib)'}", out.returncode == 0 and "Scored" in out.stdout, (out.stdout + out.stderr)[-500:])

# ---------------------------------------------------------------- overview and cleanup
s, ov = call("GET", "/api/overview")
check("overview", s == 200 and ov["latest_run"] and ov["top_alerts"], ov)
if not args.keep:
    call("DELETE", f"/api/schedules/{sched['id']}")
    for d in (ds2, ds_id):
        s, _ = call("DELETE", f"/api/datasets/{d}")
        check(f"delete dataset {d}", s == 200, _)
    for m in call("GET", "/api/models")[1]:
        if m["dataset_id"] in (ds_id, ds2):
            call("DELETE", f"/api/models/{m['model_id']}")
print("\nTIMINGS")
for label, sec in TIMES:
    print(f"  {label:32s} {sec:7.1f}s")
print("ALL PASS")
