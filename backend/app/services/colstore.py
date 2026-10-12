"""A tiny column store: one .npy file per column, memory-mapped on read.

Five million rows of int16/int32/float32 columns load in milliseconds and need no extra dependency (no Parquet,
no new compiled DLLs). A dataset directory holds `daily/`, `features/` and `truth/` column folders plus `index.npz`.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np


def preallocate(directory: Path, specs: dict[str, tuple[np.dtype, int]]) -> dict[str, np.memmap]:
    """Create writable .npy memmaps of a known final length (generator writes block by block)."""
    directory.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, (dtype, n) in specs.items():
        out[name] = np.lib.format.open_memmap(directory / f"{name}.npy", mode="w+", dtype=dtype, shape=(n,))
    return out


def flush(arrays: dict[str, np.ndarray]) -> None:
    for a in arrays.values():
        if isinstance(a, np.memmap):
            a.flush()


def write_columns(directory: Path, columns: dict[str, np.ndarray]) -> None:
    """Write whole columns atomically (a temporary folder swapped in at the end)."""
    tmp = directory.with_name(directory.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    for name, arr in columns.items():
        np.save(tmp / f"{name}.npy", np.ascontiguousarray(arr), allow_pickle=False)
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
    os.replace(tmp, directory)


def column_names(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.npy"))


def open_columns(directory: Path, names: list[str] | None = None, mmap: bool = True) -> dict[str, np.ndarray]:
    names = names or column_names(directory)
    mode = "r" if mmap else None
    return {n: np.load(directory / f"{n}.npy", mmap_mode=mode, allow_pickle=False) for n in names}


def open_column(directory: Path, name: str, mmap: bool = True) -> np.ndarray:
    return np.load(directory / f"{name}.npy", mmap_mode="r" if mmap else None, allow_pickle=False)


def save_index(path: Path, **arrays: np.ndarray) -> None:
    tmp = path.with_name(path.name + ".tmp.npz")
    np.savez(tmp, **arrays)
    os.replace(tmp, path)


def load_index(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def dir_size(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
