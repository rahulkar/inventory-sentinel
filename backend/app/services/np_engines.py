"""Pure-numpy Isolation Forest and Local Outlier Factor.

Used automatically when scikit-learn's compiled `ensemble` / `neighbors` modules cannot be imported (for example when
Windows Smart App Control blocks their DLLs). Both follow the original papers and scikit-learn's conventions closely
enough that scores rank rows the same way. Self-contained (numpy only) so it can ship inside a model bundle.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np

_EULER = 0.5772156649


def _c(n: np.ndarray | float) -> np.ndarray:
    """Average path length of an unsuccessful BST search over n points."""
    n = np.asarray(n, dtype=np.float64)
    out = np.zeros_like(n)
    big = n > 2
    out[big] = 2.0 * (np.log(n[big] - 1.0) + _EULER) - 2.0 * (n[big] - 1.0) / n[big]
    out[n == 2] = 1.0
    return out


class NumpyIsolationForest:
    def __init__(self, n_estimators: int = 100, max_samples: int = 256, random_state: int = 42) -> None:
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.random_state = random_state

    def fit(self, X: np.ndarray) -> "NumpyIsolationForest":
        X = np.asarray(X, dtype=np.float32)
        rng = np.random.default_rng(self.random_state)
        n, d = X.shape
        psi = min(self.max_samples, n)
        self.psi_ = psi
        self.max_depth_ = int(math.ceil(math.log2(max(psi, 2))))
        self.trees_ = []
        for _ in range(self.n_estimators):
            idx = rng.choice(n, size=psi, replace=False)
            self.trees_.append(self._build(X[idx], rng))
        self.c_psi_ = float(_c(np.array([psi]))[0])
        return self

    def _build(self, S: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, ...]:
        feat, thr, left, right, leaf_val = [], [], [], [], []
        stack = [(np.arange(len(S)), 0, -1, False)]
        while stack:
            rows, depth, parent, is_right = stack.pop()
            node = len(feat)
            if parent >= 0:
                (right if is_right else left)[parent] = node
            feat.append(-1)
            thr.append(0.0)
            left.append(-1)
            right.append(-1)
            leaf_val.append(0.0)
            sub = S[rows]
            if depth >= self.max_depth_ or len(rows) <= 1:
                leaf_val[node] = depth + float(_c(np.array([len(rows)]))[0])
                continue
            lo, hi = sub.min(axis=0), sub.max(axis=0)
            cand = np.flatnonzero(hi > lo)
            if len(cand) == 0:
                leaf_val[node] = depth + float(_c(np.array([len(rows)]))[0])
                continue
            q = int(rng.choice(cand))
            p = float(rng.uniform(lo[q], hi[q]))
            go_left = sub[:, q] < p
            feat[node], thr[node] = q, p
            stack.append((rows[~go_left], depth + 1, node, True))
            stack.append((rows[go_left], depth + 1, node, False))
        return (np.array(feat, np.int32), np.array(thr, np.float32), np.array(left, np.int32), np.array(right, np.int32), np.array(leaf_val, np.float32))

    def _path_lengths(self, X: np.ndarray) -> np.ndarray:
        m = len(X)
        ar = np.arange(m)
        total = np.zeros(m, dtype=np.float64)
        for feat, thr, left, right, leaf_val in self.trees_:
            node = np.zeros(m, dtype=np.int32)
            for _ in range(self.max_depth_ + 1):
                f = feat[node]
                internal = f >= 0
                if not internal.any():
                    break
                x = X[ar, np.where(internal, f, 0)]
                nxt = np.where(x < thr[node], left[node], right[node])
                node = np.where(internal, nxt, node)
            total += leaf_val[node]
        return total / len(self.trees_)

    def anomaly_score(self, X: np.ndarray, chunk: int = 50_000, workers: int = 4) -> np.ndarray:
        """2^(-E[h]/c(psi)) in (0, 1]; higher = more anomalous (= -score_samples in scikit-learn)."""
        X = np.asarray(X, dtype=np.float32)
        parts = [X[i : i + chunk] for i in range(0, len(X), chunk)]
        if len(parts) > 1 and workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                h = np.concatenate(list(ex.map(self._path_lengths, parts)))
        else:
            h = np.concatenate([self._path_lengths(p) for p in parts]) if parts else np.zeros(0)
        return np.power(2.0, -h / self.c_psi_)


class NumpyLOF:
    """Local Outlier Factor in novelty mode against a fixed reference set."""

    def __init__(self, n_neighbors: int = 35) -> None:
        self.n_neighbors = n_neighbors

    def _knn(self, Q: np.ndarray, exclude_self: bool = False, chunk: int = 2048) -> tuple[np.ndarray, np.ndarray]:
        R = self.ref_
        rn = self.ref_sq_
        k = self.n_neighbors + (1 if exclude_self else 0)
        dist_out = np.empty((len(Q), k), dtype=np.float32)
        idx_out = np.empty((len(Q), k), dtype=np.int32)
        for i in range(0, len(Q), chunk):
            q = Q[i : i + chunk]
            d2 = (q * q).sum(1)[:, None] + rn[None, :] - 2.0 * (q @ R.T)
            np.maximum(d2, 0, out=d2)
            part = np.argpartition(d2, k - 1, axis=1)[:, :k]
            dd = np.take_along_axis(d2, part, axis=1)
            order = np.argsort(dd, axis=1)
            idx_out[i : i + chunk] = np.take_along_axis(part, order, axis=1)
            dist_out[i : i + chunk] = np.sqrt(np.take_along_axis(dd, order, axis=1))
        if exclude_self:
            return dist_out[:, 1:], idx_out[:, 1:]
        return dist_out, idx_out

    def fit(self, X: np.ndarray) -> "NumpyLOF":
        self.ref_ = np.ascontiguousarray(X, dtype=np.float32)
        self.ref_sq_ = (self.ref_ * self.ref_).sum(1)
        self.n_neighbors = min(self.n_neighbors, len(self.ref_) - 1)
        dist, idx = self._knn(self.ref_, exclude_self=True)
        self.k_dist_ = dist[:, -1]
        reach = np.maximum(self.k_dist_[idx], dist)
        self.lrd_ = 1.0 / (reach.mean(1) + 1e-10)
        return self

    def _score_chunk(self, X: np.ndarray) -> np.ndarray:
        dist, idx = self._knn(X)
        reach = np.maximum(self.k_dist_[idx], dist)
        lrd = 1.0 / (reach.mean(1) + 1e-10)
        return (self.lrd_[idx].mean(1) / lrd).astype(np.float64)

    def anomaly_score(self, X: np.ndarray, chunk: int = 16_384, workers: int = 4) -> np.ndarray:
        X = np.ascontiguousarray(X, dtype=np.float32)
        parts = [X[i : i + chunk] for i in range(0, len(X), chunk)]
        if len(parts) > 1 and workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                return np.concatenate(list(ex.map(self._score_chunk, parts)))
        return np.concatenate([self._score_chunk(p) for p in parts]) if parts else np.zeros(0)
