"""The detection methods the app can train, their settings and how to build each pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.schemas import ModelSpecOut, ParamSpec
from app.services import envprobe
from app.services import features as F
from app.services.detectors import AutoencoderDetector, EnsembleDetector, IsolationForestDetector, LOFDetector, RobustZBaseline


def P(name: str, label: str, type_: str, default: Any, **kw: Any) -> ParamSpec:
    return ParamSpec(name=name, label=label, type=type_, default=default, **kw)  # type: ignore[arg-type]


def _idx(names: list[str], cols: list[str]) -> list[int]:
    return [names.index(c) for c in cols if c in names]


@dataclass
class ModelSpec:
    key: str
    label: str
    plain_label: str
    family: str
    description: str
    params: list[ParamSpec]
    build: Callable[[dict[str, Any], int, list[str], list[str]], Pipeline]  # (params, seed, feature_order, detect_features)
    fit_seconds: float
    score_seconds_per_1m: float
    recommended: bool = True
    onnx_ok: bool = True

    @property
    def engine(self) -> str:
        if self.key == "zscore":
            return "built-in rules"
        return envprobe.report()[1].get(self.key, "scikit-learn")

    @property
    def available(self) -> bool:
        return self.engine != "unavailable"

    @property
    def reason(self) -> str | None:
        if self.key == "autoencoder" and not self.available:
            return envprobe.probe("sklearn.neural_network")
        if "fallback" in self.engine:
            return "scikit-learn's compiled module is blocked on this machine; using the built-in numpy engine (same method, a little slower)."
        return None

    def to_out(self) -> ModelSpecOut:
        return ModelSpecOut(
            key=self.key, label=self.label, plain_label=self.plain_label, family=self.family, description=self.description,  # type: ignore[arg-type]
            params=self.params, recommended=self.recommended, available=self.available, reason=self.reason, engine=self.engine,
            onnx_ok=self.onnx_ok and envprobe.report()[1]["onnx"] == "available", score_seconds_per_1m=self.score_seconds_per_1m, fit_seconds=self.fit_seconds,
        )


def _zscore(params: dict[str, Any], seed: int, order: list[str], detect: list[str]) -> Pipeline:
    pre = ColumnTransformer([("pass", "passthrough", _idx(order, F.BASELINE_FEATURES))])
    return Pipeline([("pre", pre), ("model", RobustZBaseline(min_mad=float(params.get("min_mad", 0.5))))])


def _iforest(params: dict[str, Any], seed: int, order: list[str], detect: list[str]) -> Pipeline:
    pre = ColumnTransformer([("pass", "passthrough", _idx(order, detect))])
    det = IsolationForestDetector(n_estimators=int(params.get("n_estimators", 150)), max_samples=int(params.get("max_samples", 2048)), random_state=seed)
    return Pipeline([("pre", pre), ("model", det)])


def _lof(params: dict[str, Any], seed: int, order: list[str], detect: list[str]) -> Pipeline:
    pre = ColumnTransformer([("num", StandardScaler(), _idx(order, detect))])
    det = LOFDetector(n_neighbors=int(params.get("n_neighbors", 20)), reference_size=int(params.get("reference_size", 4000)), random_state=seed)
    return Pipeline([("pre", pre), ("model", det)])


def _ensemble(params: dict[str, Any], seed: int, order: list[str], detect: list[str]) -> Pipeline:
    pre = ColumnTransformer([("pass", "passthrough", _idx(order, detect))])
    det = EnsembleDetector(
        n_estimators=int(params.get("n_estimators", 150)), max_samples=int(params.get("max_samples", 2048)),
        n_neighbors=int(params.get("n_neighbors", 20)), reference_size=int(params.get("reference_size", 4000)), random_state=seed,
    )
    return Pipeline([("pre", pre), ("model", det)])


def _autoencoder(params: dict[str, Any], seed: int, order: list[str], detect: list[str]) -> Pipeline:
    pre = ColumnTransformer([("num", StandardScaler(), _idx(order, detect))])
    det = AutoencoderDetector(hidden=str(params.get("hidden", "16-4-16")), max_iter=int(params.get("max_iter", 60)), alpha=float(params.get("alpha", 1e-4)), random_state=seed)
    return Pipeline([("pre", pre), ("model", det)])


REGISTRY: dict[str, ModelSpec] = {
    "zscore": ModelSpec(
        "zscore", "Rule of thumb (robust z-score)", "Rule of thumb: unusual shrinkage for the category", "rules",
        "Flags days whose shrinkage % or stock gap is many robust standard deviations from normal for the category. The baseline every learned method must beat.",
        [P("min_mad", "Minimum spread", "float", 0.5, min=0.1, max=5, step=0.1, help="Floor on the median absolute deviation so quiet categories do not over-alert.")],
        _zscore, fit_seconds=0.2, score_seconds_per_1m=0.4,
    ),
    "iforest": ModelSpec(
        "iforest", "Isolation Forest", "Isolation forest: odd days are easy to isolate", "tree",
        "Builds many random trees that split the data; unusual days end up alone after few splits. Fast, needs no labels, handles many signals at once.",
        [
            P("n_estimators", "Trees", "int", 150, min=50, max=400, step=10, help="More trees give steadier scores and take longer."),
            P("max_samples", "Rows per tree", "int", 2048, min=256, max=8192, step=256, help="Larger samples resolve moderate anomalies better."),
        ],
        _iforest, fit_seconds=2.0, score_seconds_per_1m=21.0,
    ),
    "autoencoder": ModelSpec(
        "autoencoder", "Autoencoder", "Autoencoder: what the network cannot rebuild is unusual", "neural",
        "A small neural network (scikit-learn MLP) learns to squeeze each day through a bottleneck and rebuild it. Days it rebuilds badly are unusual.",
        [
            P("hidden", "Layers", "select", "16-4-16", options=["16-4-16", "24-6-24", "12-3-12"], help="Width of the encoder, bottleneck and decoder."),
            P("max_iter", "Training passes", "int", 60, min=10, max=200, step=10),
            P("alpha", "Regularisation", "float", 1e-4, min=0, max=0.01, step=0.0001),
        ],
        _autoencoder, fit_seconds=25.0, score_seconds_per_1m=1.0,
    ),
    "lof": ModelSpec(
        "lof", "Local Outlier Factor", "Local outlier factor: days in a sparse neighbourhood", "neighbours",
        "Compares how densely packed each day's neighbourhood is with its neighbours' neighbourhoods, against a reference sample of normal history.",
        [
            P("n_neighbors", "Neighbours", "int", 20, min=5, max=100, step=1),
            P("reference_size", "Reference rows", "int", 4000, min=1000, max=20000, step=500, help="Bigger reference sets are more accurate and slower to score."),
        ],
        _lof, fit_seconds=3.0, score_seconds_per_1m=30.0,
    ),
    "ensemble": ModelSpec(
        "ensemble", "Ensemble (Isolation Forest + LOF)", "Ensemble: Isolation Forest and LOF vote together", "ensemble",
        "Runs Isolation Forest and Local Outlier Factor side by side and adds how surprising each finds the day. They miss different problems, so together they rank real ones higher.",
        [
            P("n_estimators", "Trees", "int", 150, min=50, max=400, step=10, help="Isolation Forest trees."),
            P("max_samples", "Rows per tree", "int", 2048, min=256, max=8192, step=256),
            P("n_neighbors", "Neighbours", "int", 20, min=5, max=100, step=1, help="Local Outlier Factor neighbours."),
            P("reference_size", "Reference rows", "int", 4000, min=1000, max=20000, step=500),
        ],
        _ensemble, fit_seconds=3.0, score_seconds_per_1m=25.0, onnx_ok=False,
    ),
}


def get_spec(key: str) -> ModelSpec:
    if key not in REGISTRY:
        raise KeyError(f"Unknown method '{key}'. Available: {', '.join(REGISTRY)}")
    return REGISTRY[key]


def all_specs() -> list[ModelSpecOut]:
    return [s.to_out() for s in REGISTRY.values()]


def coerce_params(spec: ModelSpec, params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in spec.params:
        v = params.get(p.name, p.default)
        try:
            if p.type == "int":
                v = int(round(float(v)))
            elif p.type == "float":
                v = float(v)
            elif p.type == "bool":
                v = bool(v)
            elif p.type == "select" and p.options and v not in p.options:
                v = p.default
        except (TypeError, ValueError):
            v = p.default
        if p.min is not None and isinstance(v, (int, float)):
            v = max(p.min, v)
        if p.max is not None and isinstance(v, (int, float)):
            v = min(p.max, v)
        if p.type == "int":
            v = int(v)
        out[p.name] = v
    return out
