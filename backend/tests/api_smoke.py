"""End-to-end API check against a running server.

    python backend/tests/api_smoke.py [--base http://127.0.0.1:8000] [--small] [--keep]

--small uses 10 stores x 100 SKUs x 90 days (start the server with SENTINEL_MIN_ROWS=50000); the default is the full
80 x 500 x 125 = 5M-row showcase size and prints a timing table. --keep leaves the data in place.
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
ap.add_argument("--small", action="store_true")
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


size = (10, 100, 90) if args.small else (80, 500, 125)
s, h = call("GET", "/api/health")
check("health", s == 200 and h["status"] == "ok", h)
print("     engines:", h["engines"], "| issues:", len(h["env_issues"]))
s, cfg = call("GET", "/api/config")
check("config", s == 200 and cfg["min_rows"] <= size[0] * size[1] * size[2], cfg)

# ---------------------------------------------------------------- data
s, job = call("POST", "/api/datasets/generate", {"n_stores": size[0], "n_skus": size[1], "n_days": size[2], "seed": 7})
check("generate accepted", s == 202, job)
ds_id = wait_job(job, f"generate {size[0] * size[1] * size[2]:,} rows")["dataset_id"]
s, meta = call("GET", f"/api/datasets/{ds_id}")
check("dataset meta", s == 200 and meta["has_truth"] and meta["n_incidents"] > 0 and meta["n_lp_flags"] > 0, meta)
print(f"     {meta['n_rows']:,} rows, {meta['n_incidents']:,} injected incidents, {meta['n_lp_flags']} LP flags, {meta['size_bytes'] / 1e6:.0f} MB")
for t in ("daily", "stores", "skus", "lp_flags"):
    s, pv = call("GET", f"/api/datasets/{ds_id}/preview?table={t}&rows=5")
    check(f"preview {t}", s == 200 and len(pv["rows"]) > 0, pv)
s, pv = call("GET", f"/api/datasets/{ds_id}/preview?table=daily&rows=5&answer_key=true")
check("preview with answer key", "truth_type" in pv["columns"], pv["columns"])

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
s, ser = call("GET", f"/api/runs/{run_id}/series?store_id={a0['store_id']}&sku_id={a0['sku_id']}&answer_key=true")
check("series drill-down", s == 200 and len(ser["points"]) == size[2] and ser["alerts"] and ser["flagged_reasons"], {k: ser[k] for k in ("store_id", "sku_id")} if s == 200 else ser)
s, found = call("GET", f"/api/runs/{run_id}/search?q={a0['store_id']}")
check("series search", s == 200 and found, found)
s, csv = call("GET", f"/api/runs/{run_id}/alerts.csv", raw=True)
check("alerts csv", s == 200 and csv.count(b"\n") > 1, csv[:200])

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
