"""Which compiled libraries load on this machine (Windows Smart App Control can block unsigned DLLs).

Results are cached for the process; `/api/health` reports them and the registry uses them to pick engines.
"""
from __future__ import annotations

import importlib
from functools import lru_cache

PROBES = {
    "sklearn.ensemble": "scikit-learn Isolation Forest",
    "sklearn.neighbors": "scikit-learn Local Outlier Factor",
    "sklearn.neural_network": "scikit-learn MLP (autoencoder)",
    "lightgbm": "LightGBM (feedback re-ranker)",
    "onnx": "ONNX model building",
    "onnxruntime": "ONNX Runtime (export validation)",
}


@lru_cache(maxsize=None)
def probe(module: str) -> str | None:
    """None when the module imports, else a short reason."""
    try:
        importlib.import_module(module)
        return None
    except Exception as exc:  # noqa: BLE001 - ImportError or a DLL OSError
        msg = str(exc).split("\n")[0]
        if "Application Control" in msg or "blocked" in msg.lower():
            msg = "blocked by Windows Smart App Control / application control policy"
        return f"{type(exc).__name__}: {msg}"[:200]


def report() -> tuple[list[str], dict[str, str]]:
    """(issues, engines): human-readable issues and the engine each method will use."""
    issues = []
    for mod, label in PROBES.items():
        r = probe(mod)
        if r:
            issues.append(f"{label} unavailable ({mod}): {r}")
    try:
        from app import compat

        sa = probe("sqlalchemy.sql.cache_key")  # loads through the compat shim; fills PURE_FALLBACKS when binaries are blocked
        if sa:
            issues.append(f"SQLAlchemy unavailable: {sa}; assistant conversations are kept in memory only")
        elif compat.PURE_FALLBACKS:
            issues.append(f"SQLAlchemy compiled modules blocked; using its pure-Python modules ({len(compat.PURE_FALLBACKS)}) for assistant conversations")
    except ImportError:
        pass
    engines = {
        "iforest": "scikit-learn" if probe("sklearn.ensemble") is None else "numpy fallback",
        "lof": "scikit-learn" if probe("sklearn.neighbors") is None else "numpy fallback",
        "ensemble": "scikit-learn" if probe("sklearn.ensemble") is None and probe("sklearn.neighbors") is None else "numpy fallback",
        "autoencoder": "scikit-learn" if probe("sklearn.neural_network") is None else "unavailable",
        "reranker": "LightGBM" if probe("lightgbm") is None else "logistic regression fallback",
        "onnx": "available" if probe("onnx") is None and probe("onnxruntime") is None else "unavailable",
    }
    return issues, engines
