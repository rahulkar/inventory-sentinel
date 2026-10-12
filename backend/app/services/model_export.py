"""Take a trained detector out of the app: a self-contained ZIP bundle and a validated ONNX file.

ONNX graphs are built directly with the `onnx` package (no skl2onnx, which needs scikit-learn's compiled tree and
neighbour modules): tree ensembles for Isolation Forest, matrix maths + TopK for LOF, dense layers for the autoencoder,
a lookup table for the rule of thumb. Every export is validated against the Python model with onnxruntime.
"""
from __future__ import annotations

import json
import math
import os
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from app import config
from app.schemas import Job, ModelMeta, OnnxStatus
from app.services import envprobe, jobs, storage
from app.services import features as F

SERVICES = Path(__file__).resolve().parent
PINNED = ["scikit-learn", "numpy", "pandas", "joblib"]
OPSET = 17
ML_OPSET = 3


def _version(dist: str) -> str | None:
    try:
        from importlib import metadata

        return metadata.version(dist)
    except Exception:  # noqa: BLE001
        return None


def pinned_requirements(meta: ModelMeta, include_onnx: bool) -> str:
    dists = list(PINNED) + (["lightgbm"] if meta.key == "reranker" else []) + (["onnxruntime"] if include_onnx else [])
    return "\n".join(f"{d}=={_version(d)}" if _version(d) else d for d in dists) + "\n"


PREDICT_PY = r'''"""Score daily inventory records with an exported Inventory Sentinel model.

    python predict.py daily.csv scored.csv [--skus skus.csv] [--onnx]

daily.csv needs: date, store_id, sku_id, counted_closing and expected_closing (or opening_stock + received_units +
sold_units), plus whatever of received/sold/returned/adjustment/scan columns you have (see model.json "raw_columns").
Unit cost and category come from --skus (sku_id, category, unit_cost) or from columns of the same name in daily.csv.
Output adds anomaly_score, percentile, severity (none/medium/high/critical) and is_alert.
"""
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import features as F  # noqa: E402
import np_engines  # noqa: E402
import detectors  # noqa: E402

# pickled models refer to app.services.detectors / np_engines: point those names at the files in this folder
for name, mod in {"app": types.ModuleType("app"), "app.services": types.ModuleType("app.services"), "app.services.detectors": detectors, "app.services.np_engines": np_engines}.items():
    sys.modules.setdefault(name, mod)

META = json.loads((HERE / "model.json").read_text(encoding="utf-8"))


def build_features(daily: pd.DataFrame, skus: pd.DataFrame | None) -> tuple[pd.DataFrame, np.ndarray]:
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    if "expected_closing" not in df:
        df["expected_closing"] = df["opening_stock"] + df.get("received_units", 0) + df.get("returned_units", 0) - df["sold_units"] + df.get("adjustment_units", 0)
    meta_cols = ["category", "unit_cost"]
    if skus is not None:
        df = df.drop(columns=[c for c in meta_cols if c in df]).merge(skus[["sku_id"] + meta_cols], on="sku_id", how="left")
    df["category"] = df.get("category", "unknown")
    df["unit_cost"] = pd.to_numeric(df.get("unit_cost", 1.0), errors="coerce").fillna(1.0)
    df = df.sort_values(["store_id", "sku_id", "date"]).reset_index(drop=True)
    store_code, _ = pd.factorize(df["store_id"], sort=True)
    sku_code, _ = pd.factorize(df["sku_id"], sort=True)
    dates = np.sort(df["date"].unique())
    cols = {"store_code": store_code.astype(np.int64), "sku_code": sku_code.astype(np.int64), "date_idx": np.searchsorted(dates, df["date"].to_numpy())}
    for c in META["raw_columns"]:
        if c in df:
            cols[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).to_numpy()
    cats = META["categories"]
    cat = np.array([cats.index(c) if c in cats else len(cats) - 1 for c in df["category"].astype(str)])
    start = F.series_starts(cols["store_code"] * 100_000 + cols["sku_code"])
    feats = F.engineer(cols, start, df["unit_cost"].to_numpy(dtype=float), cat, df["date"].dt.dayofweek.to_numpy(), int(store_code.max()) + 1, len(dates))
    return df, F.matrix(feats, META["feature_columns"])


def score_joblib(X: np.ndarray) -> np.ndarray:
    import joblib

    pipe = joblib.load(HERE / "model.joblib")
    return detectors.pipeline_score(pipe, X)


def score_onnx(X: np.ndarray) -> np.ndarray:
    import onnxruntime as ort

    sess = ort.InferenceSession(str(HERE / "model.onnx"), providers=["CPUExecutionProvider"])
    return sess.run(None, {"features": X.astype(np.float32)})[0].ravel().astype(float)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    skus = None
    if "--skus" in sys.argv:
        skus = pd.read_csv(sys.argv[sys.argv.index("--skus") + 1], dtype={"sku_id": str})
        args = [a for a in args if a != sys.argv[sys.argv.index("--skus") + 1]]
    daily = pd.read_csv(args[0], dtype={"store_id": str, "sku_id": str})
    df, X = build_features(daily, skus)
    s = score_onnx(X) if "--onnx" in sys.argv else score_joblib(X)
    q, lv = np.asarray(META["score_quantiles"]), np.asarray(META["quantile_levels"])
    t = META["thresholds"]
    df["anomaly_score"] = np.round(s, 6)
    df["percentile"] = np.round(np.interp(s, q, lv, left=0.0, right=1.0), 6)
    df["severity"] = np.where(s >= t["critical"], "critical", np.where(s >= t["high"], "high", np.where(s >= t["alert"], "medium", "none")))
    df["is_alert"] = (s >= t["alert"]).astype(int)
    df.to_csv(args[1], index=False)
    print(f"Scored {len(df):,} rows; {int(df['is_alert'].sum()):,} alerts -> {args[1]}")


if __name__ == "__main__":
    main()
'''

BUNDLE_README = """Inventory Sentinel model bundle
================================

model.joblib     the fitted scikit-learn pipeline (feature selection + scaling + detector)
model.json       metadata: features, thresholds, score quantiles, metrics, calibration
features.py      the exact feature engineering used in the app (numpy only)
detectors.py     the detector classes the pipeline was built from
np_engines.py    numpy Isolation Forest / LOF engines (used when scikit-learn's compiled modules are blocked)
predict.py       score a daily inventory CSV (see the top of the file)
requirements.txt pinned library versions the joblib file was saved with
model.onnx       (when exported) the same model as an ONNX graph: input "features" float32 [n, %d] in the order of
                 model.json "feature_columns"; output "anomaly_score" [n]; no Python needed (onnxruntime in C#, Java, JS...)

Quick start:
    python -m pip install -r requirements.txt
    python predict.py daily.csv scored.csv --skus skus.csv
    python predict.py daily.csv scored.csv --skus skus.csv --onnx
""" % len(F.FEATURES)


def bundle_filename(meta: ModelMeta) -> str:
    return f"inventory_sentinel_{meta.key}_{meta.model_id}.zip"


def build_bundle(model_id: str, force: bool = False) -> tuple[Path, str]:
    meta = storage.get_model(model_id)
    if meta is None:
        raise LookupError("Model not found.")
    paths = storage.model_paths(model_id)
    out = paths["bundle"]
    out.parent.mkdir(parents=True, exist_ok=True)
    sources = [paths["pipeline"], paths["meta"]] + ([paths["onnx"]] if paths["onnx"].exists() else [])
    newest = max(p.stat().st_mtime for p in sources if p.exists())
    if out.exists() and not force and out.stat().st_mtime >= newest:
        return out, bundle_filename(meta)
    has_onnx = paths["onnx"].exists()
    model_json = json.loads(meta.model_dump_json())
    from app.services.synth import DAILY_SPECS

    model_json["raw_columns"] = [c for c in DAILY_SPECS if c not in ("date_idx", "store_code", "sku_code")]
    tmp = out.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=config.EXPORT_COMPRESSLEVEL) as zf:
            zf.write(paths["pipeline"], "model.joblib")
            zf.writestr("model.json", json.dumps(model_json, indent=1))
            for f in ("features.py", "detectors.py", "np_engines.py"):
                zf.write(SERVICES / f, f)
            zf.writestr("requirements.txt", pinned_requirements(meta, has_onnx))
            zf.writestr("predict.py", PREDICT_PY)
            zf.writestr("README.txt", BUNDLE_README)
            if has_onnx:
                zf.write(paths["onnx"], "model.onnx")
                if paths["onnx_meta"].exists():
                    zf.write(paths["onnx_meta"], "model.onnx.json")
        os.replace(tmp, out)
    except BaseException:
        storage.safe_unlink(tmp)
        raise
    return out, bundle_filename(meta)


# ---------------------------------------------------------------- ONNX graph builders
def _onnx_libs() -> tuple[bool, str | None]:
    for mod in ("onnx", "onnxruntime"):
        r = envprobe.probe(mod)
        if r:
            return False, f"{mod} cannot load: {r}"
    return True, None


def onnx_supported(meta: ModelMeta, pipe: Any) -> tuple[bool, str | None]:
    ok, reason = _onnx_libs()
    if not ok:
        return False, reason
    if meta.key == "reranker":
        return False, "The feedback re-ranker chains two models (a detector and LightGBM); use the joblib bundle."
    return True, None


def _cols_of(pipe: Any) -> tuple[list[int], Any]:
    """(selected column indices, scaler or None) from the 'pre' ColumnTransformer."""
    ct = pipe.named_steps["pre"]
    name, trans, cols = ct.transformers_[0]
    return [int(c) for c in cols], (trans if hasattr(trans, "mean_") else None)


def _graph(nodes: list, inits: list, n_features: int, opset_ml: bool = False):
    import onnx
    from onnx import TensorProto, helper

    graph = helper.make_graph(
        nodes, "inventory_sentinel",
        [helper.make_tensor_value_info("features", TensorProto.FLOAT, [None, n_features])],
        [helper.make_tensor_value_info("anomaly_score", TensorProto.FLOAT, [None])],
        initializer=inits,
    )
    opsets = [helper.make_opsetid("", OPSET)] + ([helper.make_opsetid("ai.onnx.ml", ML_OPSET)] if opset_ml else [])
    model = helper.make_model(graph, opset_imports=opsets, producer_name="inventory-sentinel")
    model.ir_version = min(model.ir_version, 9)
    onnx.checker.check_model(model)
    return model


def _t(name: str, arr: np.ndarray):
    from onnx import numpy_helper

    return numpy_helper.from_array(np.asarray(arr), name=name)


def _select_and_scale(pipe: Any, nodes: list, inits: list) -> str:
    from onnx import helper

    cols, scaler = _cols_of(pipe)
    inits.append(_t("cols", np.array(cols, dtype=np.int64)))
    nodes.append(helper.make_node("Gather", ["features", "cols"], ["x_sel"], axis=1))
    if scaler is None:
        return "x_sel"
    inits += [_t("mu", scaler.mean_.astype(np.float32)), _t("sd", scaler.scale_.astype(np.float32))]
    nodes += [helper.make_node("Sub", ["x_sel", "mu"], ["x_c"]), helper.make_node("Div", ["x_c", "sd"], ["x_s"])]
    return "x_s"


def _build_zscore(pipe: Any, n_features: int):
    from onnx import helper

    det = pipe.named_steps["model"]
    nodes, inits = [], []
    x = _select_and_scale(pipe, nodes, inits)
    inits += [
        _t("med", det.med_.astype(np.float32)), _t("mad", det.mad_.astype(np.float32)),
        _t("i01", np.array([0, 1], dtype=np.int64)), _t("i2", np.array([2], dtype=np.int64)),
        _t("cmax", np.array(det.n_cat_ - 1, dtype=np.float32)), _t("czero", np.array(0, dtype=np.float32)),
    ]
    nodes += [
        helper.make_node("Gather", [x, "i01"], ["v"], axis=1),
        helper.make_node("Gather", [x, "i2"], ["c2"], axis=1),
        helper.make_node("Clip", ["c2", "czero", "cmax"], ["c2c"]),
        helper.make_node("Squeeze", ["c2c", "i2_axes"], ["cf"]),
        helper.make_node("Cast", ["cf"], ["ci"], to=7),
        helper.make_node("Gather", ["med", "ci"], ["m"], axis=0),
        helper.make_node("Gather", ["mad", "ci"], ["s"], axis=0),
        helper.make_node("Sub", ["v", "m"], ["d"]),
        helper.make_node("Div", ["d", "s"], ["z"]),
        helper.make_node("Abs", ["z"], ["az"]),
        helper.make_node("ReduceMax", ["az"], ["anomaly_score"], axes=[1], keepdims=0),
    ]
    inits.append(_t("i2_axes", np.array([1], dtype=np.int64)))
    return _graph(nodes, inits, n_features)


def _c(n: float) -> float:
    if n > 2:
        return 2.0 * (math.log(n - 1.0) + 0.5772156649) - 2.0 * (n - 1.0) / n
    return 1.0 if n == 2 else 0.0


def _forest_arrays(det: Any) -> tuple[list[tuple], float, str]:
    """[(feat, thr, left, right, leaf_value)] per tree, normaliser c(psi), and the branch mode."""
    inner = det.inner_
    if det.engine_ == "numpy":
        return [tuple(np.asarray(a) for a in t) for t in inner.trees_], inner.c_psi_ * len(inner.trees_), "BRANCH_LT"
    trees = []
    for est, feats in zip(inner.estimators_, inner.estimators_features_):
        tr = est.tree_
        n = tr.node_count
        depth = np.zeros(n)
        for i in range(n):
            for ch in (tr.children_left[i], tr.children_right[i]):
                if ch >= 0:
                    depth[ch] = depth[i] + 1
        leaf = tr.children_left < 0
        leaf_val = np.where(leaf, depth + np.array([_c(float(s)) for s in tr.n_node_samples]), 0.0)
        feat = np.where(leaf, -1, np.asarray(feats)[np.maximum(tr.feature, 0)])
        trees.append((feat, tr.threshold.astype(np.float32), tr.children_left, tr.children_right, leaf_val))
    return trees, _c(float(inner.max_samples_)) * len(trees), "BRANCH_LEQ"


def _build_iforest(pipe: Any, n_features: int):
    from onnx import helper

    det = pipe.named_steps["model"]
    trees, norm, mode = _forest_arrays(det)
    nodes, inits = [], []
    x = _select_and_scale(pipe, nodes, inits)
    a: dict[str, list] = {k: [] for k in ("tid", "nid", "fid", "mode", "val", "tnode", "fnode", "lt", "ln", "lw")}
    for t, (feat, thr, left, right, leaf_val) in enumerate(trees):
        for i in range(len(feat)):
            a["tid"].append(t)
            a["nid"].append(i)
            if feat[i] < 0:
                a["fid"].append(0)
                a["mode"].append("LEAF")
                a["val"].append(0.0)
                a["tnode"].append(0)
                a["fnode"].append(0)
                a["lt"].append(t)
                a["ln"].append(i)
                a["lw"].append(float(leaf_val[i]))
            else:
                a["fid"].append(int(feat[i]))
                a["mode"].append(mode)
                a["val"].append(float(thr[i]))
                a["tnode"].append(int(left[i]))
                a["fnode"].append(int(right[i]))
    nodes.append(helper.make_node(
        "TreeEnsembleRegressor", [x], ["path_sum"], domain="ai.onnx.ml", n_targets=1, aggregate_function="SUM", post_transform="NONE",
        nodes_treeids=a["tid"], nodes_nodeids=a["nid"], nodes_featureids=a["fid"], nodes_modes=a["mode"], nodes_values=a["val"],
        nodes_truenodeids=a["tnode"], nodes_falsenodeids=a["fnode"], target_ids=[0] * len(a["lt"]), target_treeids=a["lt"], target_nodeids=a["ln"], target_weights=a["lw"],
    ))
    # anomaly = 2 ** (-mean_path / c(psi)) = exp(-sum_path * ln2 / (T * c(psi)))
    inits += [_t("k", np.array(-math.log(2.0) / norm, dtype=np.float32)), _t("ax1", np.array([1], dtype=np.int64))]
    nodes += [helper.make_node("Mul", ["path_sum", "k"], ["e"]), helper.make_node("Exp", ["e"], ["s2"]), helper.make_node("Squeeze", ["s2", "ax1"], ["anomaly_score"])]
    return _graph(nodes, inits, n_features, opset_ml=True)


def _build_lof(pipe: Any, n_features: int):
    from onnx import helper

    det = pipe.named_steps["model"]
    inner = det.inner_
    if det.engine_ == "numpy":
        R, kd, lrd, k = inner.ref_, inner.k_dist_, inner.lrd_, inner.n_neighbors
    else:
        R, k = inner._fit_X, inner.n_neighbors_
        kd, lrd = inner._distances_fit_X_[:, k - 1], inner._lrd
    nodes, inits = [], []
    x = _select_and_scale(pipe, nodes, inits)
    inits += [
        _t("Rt", np.ascontiguousarray(np.asarray(R, dtype=np.float32).T)), _t("rsq", (np.asarray(R, dtype=np.float32) ** 2).sum(1)[None, :]),
        _t("kd", np.asarray(kd, dtype=np.float32)), _t("lrd", np.asarray(lrd, dtype=np.float32)), _t("K", np.array([k], dtype=np.int64)),
        _t("two", np.array(2.0, dtype=np.float32)), _t("zero", np.array(0.0, dtype=np.float32)), _t("eps", np.array(1e-10, dtype=np.float32)), _t("one", np.array(1.0, dtype=np.float32)),
    ]
    nodes += [
        helper.make_node("ReduceSumSquare", [x], ["xsq"], axes=[1], keepdims=1),
        helper.make_node("MatMul", [x, "Rt"], ["xr"]),
        helper.make_node("Mul", ["xr", "two"], ["xr2"]),
        helper.make_node("Add", ["xsq", "rsq"], ["s"]),
        helper.make_node("Sub", ["s", "xr2"], ["d2"]),
        helper.make_node("Max", ["d2", "zero"], ["d2p"]),
        helper.make_node("TopK", ["d2p", "K"], ["nd2", "nidx"], axis=1, largest=0, sorted=1),
        helper.make_node("Sqrt", ["nd2"], ["nd"]),
        helper.make_node("Gather", ["kd", "nidx"], ["nkd"], axis=0),
        helper.make_node("Max", ["nkd", "nd"], ["reach"]),
        helper.make_node("ReduceMean", ["reach"], ["mreach"], axes=[1], keepdims=0),
        helper.make_node("Add", ["mreach", "eps"], ["mreach_e"]),
        helper.make_node("Div", ["one", "mreach_e"], ["lrd_x"]),
        helper.make_node("Gather", ["lrd", "nidx"], ["nlrd"], axis=0),
        helper.make_node("ReduceMean", ["nlrd"], ["mlrd"], axes=[1], keepdims=0),
        helper.make_node("Div", ["mlrd", "lrd_x"], ["anomaly_score"]),
    ]
    return _graph(nodes, inits, n_features)


def _build_autoencoder(pipe: Any, n_features: int):
    from onnx import helper

    mlp = pipe.named_steps["model"].inner_
    nodes, inits = [], []
    x = _select_and_scale(pipe, nodes, inits)
    h = x
    for i, (W, b) in enumerate(zip(mlp.coefs_, mlp.intercepts_)):
        inits += [_t(f"W{i}", W.astype(np.float32)), _t(f"b{i}", b.astype(np.float32))]
        nodes += [helper.make_node("MatMul", [h, f"W{i}"], [f"mm{i}"]), helper.make_node("Add", [f"mm{i}", f"b{i}"], [f"z{i}"])]
        h = f"z{i}"
        if i < len(mlp.coefs_) - 1:
            nodes.append(helper.make_node("Relu", [h], [f"a{i}"]))
            h = f"a{i}"
    nodes += [helper.make_node("Sub", [h, x], ["err"]), helper.make_node("Mul", ["err", "err"], ["sq"]), helper.make_node("ReduceMean", ["sq"], ["anomaly_score"], axes=[1], keepdims=0)]
    return _graph(nodes, inits, n_features)


BUILDERS = {"zscore": _build_zscore, "iforest": _build_iforest, "lof": _build_lof, "autoencoder": _build_autoencoder}


def onnx_status(model_id: str) -> OnnxStatus:
    meta = storage.get_model(model_id)
    if meta is None:
        raise LookupError("Model not found.")
    paths = storage.model_paths(model_id)
    if not paths["onnx"].exists():
        return OnnxStatus(model_id=model_id, available=meta.onnx_ok, ready=False, reason=meta.onnx_reason)
    info: dict[str, Any] = {}
    if paths["onnx_meta"].exists():
        try:
            info = json.loads(paths["onnx_meta"].read_text(encoding="utf-8"))
        except ValueError:
            info = {}
    return OnnxStatus(
        model_id=model_id, available=True, ready=True, size_bytes=storage.file_size(paths["onnx"]), created_at=info.get("created_at"),
        max_abs_diff=info.get("max_abs_diff"), spearman=info.get("spearman"), top1_overlap=info.get("top1_overlap"), n_checked=info.get("n_checked"), warnings=info.get("warnings", []),
    )


def _ranks(a: np.ndarray) -> np.ndarray:
    r = np.empty(len(a))
    r[np.argsort(a, kind="stable")] = np.arange(len(a))
    return r


def convert_to_onnx(model_id: str, ctx: jobs.JobContext | None = None, n_validate: int = 2000) -> dict[str, Any]:
    import onnxruntime as ort

    from app.services.detectors import pipeline_score

    meta = storage.get_model(model_id)
    if meta is None:
        raise LookupError("Model not found.")
    if not meta.onnx_ok or meta.key not in BUILDERS:
        raise RuntimeError(meta.onnx_reason or "This model cannot be exported to ONNX.")
    pipe = storage.load_pipeline(model_id)
    if ctx:
        ctx.step("convert", "Building the ONNX graph")
    model = BUILDERS[meta.key](pipe, len(F.FEATURES))
    paths = storage.model_paths(model_id)
    tmp = paths["onnx"].with_suffix(".onnx.tmp")
    tmp.write_bytes(model.SerializeToString())
    if ctx:
        ctx.progress(50)
        ctx.step("validate", "Checking ONNX against the Python model")
    ds = storage.load_dataset(meta.dataset_id)
    rng = np.random.default_rng(0)
    rows = np.sort(rng.choice(ds.meta.n_rows, size=min(n_validate, ds.meta.n_rows), replace=False))
    from app.services.training import feature_matrix

    X = feature_matrix(ds, rows)
    ref = pipeline_score(pipe, X)
    sess = ort.InferenceSession(str(tmp), providers=["CPUExecutionProvider"])
    got = sess.run(None, {"features": X.astype(np.float32)})[0].ravel().astype(np.float64)
    diff = np.abs(got - ref)
    spearman = float(np.corrcoef(_ranks(got), _ranks(ref))[0, 1])
    top = max(1, len(ref) // 100)
    overlap = len(set(np.argsort(-got)[:top]) & set(np.argsort(-ref)[:top])) / top
    warnings = []
    if spearman < 0.999 or overlap < 0.98:
        storage.safe_unlink(tmp)
        raise RuntimeError(f"ONNX output does not match the Python model closely enough (rank correlation {spearman:.4f}, top-1% overlap {overlap:.2f}).")
    if diff.max() > 1e-3 * max(1.0, float(np.abs(ref).max())):
        warnings.append(f"Largest absolute score difference {diff.max():.2e} (float32 arithmetic); rankings agree.")
    os.replace(tmp, paths["onnx"])
    info = {"created_at": storage.now_iso(), "opset": OPSET, "n_checked": int(len(rows)), "max_abs_diff": float(diff.max()), "mean_abs_diff": float(diff.mean()), "spearman": round(spearman, 6), "top1_overlap": round(overlap, 4), "warnings": warnings}
    storage.atomic_write_text(paths["onnx_meta"], json.dumps(info, indent=1))
    storage.safe_unlink(paths["bundle"])
    return {"model_id": model_id, **info}


def start_onnx_job(model_id: str) -> Job:
    meta = storage.get_model(model_id)
    if meta is None:
        raise LookupError("Model not found.")
    if not meta.onnx_ok:
        raise RuntimeError(meta.onnx_reason or "This model cannot be exported to ONNX.")
    return jobs.submit(
        "export", f"Export {meta.label} to ONNX", lambda ctx: convert_to_onnx(model_id, ctx), params={"model_id": model_id},
        steps=[("convert", "Building the ONNX graph"), ("validate", "Checking ONNX against the Python model")], estimate_seconds=20,
    )
