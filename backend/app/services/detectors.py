"""Anomaly detectors with one contract: `fit(X)` and `anomaly_score(X)` (higher = more unusual).

Every detector sits behind a `pre` ColumnTransformer in a scikit-learn Pipeline (step names "pre" and "model").
scikit-learn's compiled ensemble/neighbors modules are imported lazily; when they cannot load (Windows Smart App
Control can block their DLLs) the detector falls back to the pure-numpy engine and records `engine_ = "numpy"`.
This file ships verbatim inside model bundles, so it imports nothing from the app.
"""
from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator


def _np_engines():
    try:
        from app.services import np_engines  # inside the app
    except ImportError:  # inside an exported bundle (np_engines.py sits next to predict.py)
        import np_engines  # type: ignore[no-redef]
    return np_engines


def pipeline_score(pipe, X: np.ndarray) -> np.ndarray:
    """Anomaly score of a fitted Pipeline([("pre", ...), ("model", detector)])."""
    Xt = pipe.named_steps["pre"].transform(X)
    return np.asarray(pipe.named_steps["model"].anomaly_score(np.asarray(Xt, dtype=np.float32)), dtype=np.float64)


class RobustZBaseline(BaseEstimator):
    """Rule of thumb: how many robust standard deviations is today's shrinkage from normal for this category?

    Expects three passthrough columns: shrinkage %, variance units, category code.
    """

    def __init__(self, min_mad: float = 0.5) -> None:
        self.min_mad = min_mad

    def fit(self, X, y=None):
        X = np.asarray(X, dtype=np.float64)
        cats = X[:, 2].astype(int)
        self.n_cat_ = int(cats.max()) + 1 if len(cats) else 1
        self.med_ = np.zeros((self.n_cat_, 2))
        self.mad_ = np.ones((self.n_cat_, 2))
        for c in range(self.n_cat_):
            sub = X[cats == c, :2]
            if len(sub) == 0:
                continue
            med = np.median(sub, axis=0)
            self.med_[c] = med
            self.mad_[c] = np.maximum(np.median(np.abs(sub - med), axis=0) * 1.4826, self.min_mad)
        self.engine_ = "rules"
        return self

    def anomaly_score(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        c = np.clip(X[:, 2].astype(int), 0, self.n_cat_ - 1)
        z = (X[:, :2] - self.med_[c]) / self.mad_[c]
        return np.abs(z).max(axis=1)


class IsolationForestDetector(BaseEstimator):
    def __init__(self, n_estimators: int = 150, max_samples: int = 2048, random_state: int = 42, engine: str = "auto") -> None:
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.random_state = random_state
        self.engine = engine

    def fit(self, X, y=None):
        X = np.asarray(X, dtype=np.float32)
        self.engine_ = "numpy"
        if self.engine in ("auto", "sklearn"):
            try:
                from sklearn.ensemble import IsolationForest

                self.inner_ = IsolationForest(n_estimators=self.n_estimators, max_samples=min(self.max_samples, len(X)), random_state=self.random_state, n_jobs=-1).fit(X)
                self.engine_ = "sklearn"
                return self
            except ImportError as exc:
                if self.engine == "sklearn":
                    raise
                self.fallback_reason_ = f"{type(exc).__name__}: {exc}"
        self.inner_ = _np_engines().NumpyIsolationForest(self.n_estimators, self.max_samples, self.random_state).fit(X)
        return self

    def anomaly_score(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        if self.engine_ == "sklearn":
            return -self.inner_.score_samples(X)
        return self.inner_.anomaly_score(X)


class LOFDetector(BaseEstimator):
    def __init__(self, n_neighbors: int = 20, reference_size: int = 4000, random_state: int = 42, engine: str = "auto") -> None:
        self.n_neighbors = n_neighbors
        self.reference_size = reference_size
        self.random_state = random_state
        self.engine = engine

    def fit(self, X, y=None):
        X = np.asarray(X, dtype=np.float32)
        rng = np.random.default_rng(self.random_state)
        if len(X) > self.reference_size:
            X = X[rng.choice(len(X), self.reference_size, replace=False)]
        self.engine_ = "numpy"
        if self.engine in ("auto", "sklearn"):
            try:
                from sklearn.neighbors import LocalOutlierFactor

                self.inner_ = LocalOutlierFactor(n_neighbors=self.n_neighbors, novelty=True, n_jobs=-1).fit(X)
                self.engine_ = "sklearn"
                return self
            except ImportError as exc:
                if self.engine == "sklearn":
                    raise
                self.fallback_reason_ = f"{type(exc).__name__}: {exc}"
        self.inner_ = _np_engines().NumpyLOF(self.n_neighbors).fit(X)
        return self

    def anomaly_score(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        if self.engine_ == "sklearn":
            return -self.inner_.score_samples(X)
        return self.inner_.anomaly_score(X)


class AutoencoderDetector(BaseEstimator):
    """A small dense autoencoder (scikit-learn MLP trained to reproduce its input); score = reconstruction error."""

    def __init__(self, hidden: str = "16-4-16", alpha: float = 1e-4, max_iter: int = 60, batch_size: int = 512, learning_rate_init: float = 1e-3, random_state: int = 42) -> None:
        self.hidden = hidden
        self.alpha = alpha
        self.max_iter = max_iter
        self.batch_size = batch_size
        self.learning_rate_init = learning_rate_init
        self.random_state = random_state

    def fit(self, X, y=None):
        import warnings

        from sklearn.exceptions import ConvergenceWarning
        from sklearn.neural_network import MLPRegressor

        X = np.asarray(X, dtype=np.float32)
        layers = tuple(int(h) for h in str(self.hidden).split("-") if h)
        self.inner_ = MLPRegressor(hidden_layer_sizes=layers, activation="relu", alpha=self.alpha, batch_size=self.batch_size, learning_rate_init=self.learning_rate_init, max_iter=self.max_iter, early_stopping=True, n_iter_no_change=6, random_state=self.random_state)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            self.inner_.fit(X, X)
        self.engine_ = "sklearn"
        return self

    def per_feature_error(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        return (self.inner_.predict(X) - X) ** 2

    def anomaly_score(self, X, chunk: int = 200_000) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        out = np.empty(len(X), dtype=np.float64)
        for i in range(0, len(X), chunk):
            out[i : i + chunk] = self.per_feature_error(X[i : i + chunk]).mean(axis=1)
        return out


class FeedbackReranker(BaseEstimator):
    """Blend of a base detector's percentile and a supervised model trained on team feedback (see services/reranker.py).

    `anomaly_score` expects the *raw* feature matrix (it is used as a pipeline step after a passthrough `pre`).
    """

    def __init__(self, alpha: float = 0.4) -> None:
        self.alpha = alpha

    def setup(self, base_pipe, clf, base_quantiles: np.ndarray, base_levels: np.ndarray) -> "FeedbackReranker":
        self.base_pipe_ = base_pipe
        self.clf_ = clf
        self.base_quantiles_ = np.asarray(base_quantiles, dtype=np.float64)
        self.base_levels_ = np.asarray(base_levels, dtype=np.float64)
        self.engine_ = getattr(base_pipe.named_steps["model"], "engine_", "sklearn")
        return self

    def fit(self, X, y=None):
        return self

    def base_percentile(self, X) -> np.ndarray:
        s = pipeline_score(self.base_pipe_, X)
        return np.interp(s, self.base_quantiles_, self.base_levels_, left=0.0, right=1.0)

    def anomaly_score(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        pct = self.base_percentile(X)
        Z = np.column_stack([X, pct.astype(np.float32)])
        p = self.clf_.predict_proba(Z)[:, 1]
        return self.alpha * pct + (1 - self.alpha) * p
