"""Import real inventory data (CSV) or an exported Inventory Sentinel bundle (ZIP) into the column store."""
from __future__ import annotations

import gc
import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from app import config
from app.schemas import DatasetMeta, Detection
from app.services import colstore, datasets, storage, synth

ALIASES: dict[str, list[str]] = {
    "date": ["date", "count_date", "business_date", "txn_date", "day", "trading_date", "stock_date"],
    "store_id": ["store_id", "store", "site", "site_id", "location", "location_id", "branch", "shop"],
    "sku_id": ["sku_id", "sku", "item", "item_id", "article", "article_id", "product_id", "product", "ean", "barcode"],
    "counted_closing": ["counted_closing", "counted", "count_qty", "physical_qty", "soh_counted", "closing_count", "counted_qty", "on_hand"],
    "expected_closing": ["expected_closing", "expected", "book_qty", "system_qty", "soh_system", "book_stock", "system_stock"],
    "opening_stock": ["opening_stock", "opening", "open_qty", "opening_qty", "start_stock"],
    "received_units": ["received_units", "received", "receipts", "delivered", "goods_in", "receipt_qty"],
    "sold_units": ["sold_units", "sold", "sales_units", "units_sold", "sales_qty", "qty_sold"],
    "returned_units": ["returned_units", "returned", "returns", "return_qty", "refund_units"],
    "transfer_in_units": ["transfer_in_units", "transfer_in", "transfers_in", "tfr_in"],
    "transfer_out_units": ["transfer_out_units", "transfer_out", "transfers_out", "tfr_out"],
    "adjustment_units": ["adjustment_units", "adjustment", "adjustments", "adj_qty", "write_off", "write_offs"],
    "pos_scans": ["pos_scans", "scans", "till_scans", "pos_lines", "scan_count"],
    "manual_entry_scans": ["manual_entry_scans", "manual_entries", "manual_scans", "keyed_entries", "keyed_scans"],
    "void_count": ["void_count", "voids", "void_lines", "voided"],
    "override_count": ["override_count", "overrides", "price_overrides"],
    "after_hours_scans": ["after_hours_scans", "after_hours", "out_of_hours_scans"],
    "receiving_scans": ["receiving_scans", "received_scanned", "goods_in_scans", "receipt_scans"],
    "on_promo": ["on_promo", "promo", "promotion", "is_promo", "on_promotion"],
    "category": ["category", "department", "dept", "product_category"],
    "unit_cost": ["unit_cost", "cost", "cost_price", "unit_cost_gbp"],
}
REQUIRED = ["date", "store_id", "sku_id", "counted_closing"]
MEASURES = [c for c in synth.DAILY_SPECS if c not in ("date_idx", "store_code", "sku_code")]


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def detect_columns(columns: list[str], override: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    """Map our field -> the file's column. Returns (column_map, missing optional fields)."""
    norm = {normalize(c): c for c in columns}
    cmap: dict[str, str] = {}
    for field, aliases in ALIASES.items():
        for a in aliases:
            if a in norm:
                cmap[field] = norm[a]
                break
    for k, v in (override or {}).items():
        if v and v in columns:
            cmap[k] = v
    missing = [f for f in ALIASES if f not in cmap and f not in REQUIRED]
    return cmap, missing


def _sniff_sep(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
        head = fh.readline()
    return max([",", ";", "\t", "|"], key=head.count)


def _pick_files(folder: Path) -> dict[str, Path | None]:
    csvs = sorted(folder.rglob("*.csv"), key=lambda p: -p.stat().st_size)
    by_name = {p.name.lower(): p for p in csvs}
    daily = next((p for n, p in by_name.items() if n.startswith(("daily", "inventory", "stock"))), csvs[0] if csvs else None)
    return {
        "daily": daily,
        "stores": by_name.get("stores.csv"),
        "skus": by_name.get("skus.csv"),
        "lp_flags": by_name.get("lp_flags.csv"),
        "answer_key": by_name.get("answer_key.csv"),
        "metadata": next(iter(folder.rglob("metadata.json")), None),
    }


def process(ds_id: str, src: Path | None, is_zip: bool, name: str | None, override: dict[str, str] | None, on_progress: Callable[[float, str], None], check: Callable[[], None]) -> DatasetMeta:
    """Import `src` (CSV or ZIP) into dataset `ds_id`; with src=None, re-process the raw files kept from the first import."""
    ds_dir = storage.dataset_dir(ds_id)
    raw_dir = ds_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    if src is None:
        files = _pick_files(raw_dir)
        # release the cached memory maps first: Windows cannot delete or overwrite a mapped file
        storage._dataset_cache.pop(ds_id)
        gc.collect()
        for sub in ("daily", "features", "truth"):
            storage.safe_rmtree(ds_dir / sub)
    elif is_zip:
        on_progress(0.02, "Unpacking the ZIP")
        with zipfile.ZipFile(src) as zf:
            for m in zf.infolist():
                if m.is_dir() or ".." in m.filename or m.filename.startswith("/"):
                    continue
                if not m.filename.lower().endswith((".csv", ".json")):
                    continue
                target = raw_dir / Path(m.filename).name
                with zf.open(m) as fin, target.open("wb") as fout:
                    shutil.copyfileobj(fin, fout, 1 << 20)
        files = _pick_files(raw_dir)
    else:
        target = raw_dir / "daily.csv"
        if src != target:
            shutil.move(str(src), target)
        files = {"daily": target, "stores": None, "skus": None, "lp_flags": None, "answer_key": None, "metadata": None}
    if files["daily"] is None:
        raise ValueError("No CSV file found in the upload.")
    daily_path: Path = files["daily"]  # type: ignore[assignment]
    sep = _sniff_sep(daily_path)
    head = pd.read_csv(daily_path, sep=sep, nrows=config.UPLOAD_SAMPLE_ROWS, encoding="utf-8-sig")
    cmap, missing = detect_columns(list(head.columns), override)
    lacking = [f for f in REQUIRED if f not in cmap]
    if "expected_closing" not in cmap and not all(k in cmap for k in ("opening_stock", "sold_units")):
        lacking.append("expected_closing (or opening_stock + sold_units)")
    if lacking:
        raise ValueError(f"Could not find required column(s): {', '.join(lacking)}. Columns in the file: {', '.join(map(str, head.columns[:30]))}. Map them with the 'column map' option.")
    # ---- read in chunks; ids and dates as categories mapped to global codes
    use = sorted(set(cmap.values()))
    total_bytes = max(daily_path.stat().st_size, 1)
    store_codes: dict[str, int] = {}
    sku_codes: dict[str, int] = {}
    parts: dict[str, list[np.ndarray]] = {k: [] for k in ["store", "sku", "day"] + [f for f in MEASURES + ["category", "unit_cost"] if f in cmap]}
    sku_meta: dict[str, tuple[str, float]] = {}
    read_bytes = 0
    dtype = {cmap["store_id"]: "category", cmap["sku_id"]: "category", cmap["date"]: "category"}
    if "category" in cmap:
        dtype[cmap["category"]] = "category"
    for chunk in pd.read_csv(daily_path, sep=sep, usecols=use, dtype=dtype, chunksize=config.CSV_READ_CHUNK_ROWS, encoding="utf-8-sig"):
        check()
        for key, codes_map, col in (("store", store_codes, cmap["store_id"]), ("sku", sku_codes, cmap["sku_id"])):
            cats = [str(c) for c in chunk[col].cat.categories]
            lut = np.array([codes_map.setdefault(c, len(codes_map)) for c in cats] + [-1], dtype=np.int64)
            parts[key].append(lut[chunk[col].cat.codes.to_numpy()])
        dcats = pd.to_datetime(pd.Series(chunk[cmap["date"]].cat.categories.astype(str)), errors="coerce", dayfirst=False)
        dlut = np.r_[(dcats.to_numpy().astype("datetime64[D]").astype(np.int64)), -1]
        parts["day"].append(dlut[chunk[cmap["date"]].cat.codes.to_numpy()])
        for f in MEASURES:
            if f in cmap:
                v = pd.to_numeric(chunk[cmap[f]], errors="coerce")
                if f == "on_promo":
                    v = v.fillna(0).clip(0, 1)
                parts[f].append(v.fillna(0).round().to_numpy(dtype=np.int64))
        if "category" in cmap or "unit_cost" in cmap:
            sid = chunk[cmap["sku_id"]].astype(str).to_numpy()
            cat = chunk[cmap["category"]].astype(str).to_numpy() if "category" in cmap else np.full(len(chunk), "unknown")
            cost = pd.to_numeric(chunk[cmap["unit_cost"]], errors="coerce").fillna(1.0).to_numpy() if "unit_cost" in cmap else np.ones(len(chunk))
            _, first = np.unique(sid, return_index=True)
            for i in first:
                sku_meta.setdefault(sid[i], (cat[i], float(cost[i])))
        read_bytes += int(chunk.memory_usage(deep=False).sum())
        on_progress(min(0.4, 0.05 + 0.35 * read_bytes / (total_bytes * 2.5)), f"Read {sum(len(p) for p in parts['store']):,} rows")
    store = np.concatenate(parts["store"])
    sku = np.concatenate(parts["sku"])
    day = np.concatenate(parts["day"])
    ok = (store >= 0) & (sku >= 0) & (day >= 0)
    if not ok.all():
        warnings.append(f"Dropped {int((~ok).sum()):,} rows with a missing store, SKU or unparseable date.")
    meas = {f: np.concatenate(parts[f])[ok] for f in MEASURES if f in cmap}
    store, sku, day = store[ok], sku[ok], day[ok]
    if len(day) == 0:
        raise ValueError("No usable rows: every row is missing a store, a SKU or a date that could be read. Check the date format and the column map.")
    # stable codes in sorted-id order
    st_ids = sorted(store_codes, key=lambda s: (len(s), s))
    sk_ids = sorted(sku_codes, key=lambda s: (len(s), s))
    code_max = np.iinfo(np.int16).max  # store_code / sku_code / date_idx are stored as int16
    if len(st_ids) > code_max or len(sk_ids) > code_max or int(day.max() - day.min()) > code_max:
        raise ValueError(f"Too many distinct values: {len(st_ids):,} stores, {len(sk_ids):,} SKUs, {int(day.max() - day.min()) + 1:,} days (each must be at most {code_max:,}).")
    st_remap = np.empty(len(store_codes), dtype=np.int64)
    st_remap[[store_codes[s] for s in st_ids]] = np.arange(len(st_ids))
    sk_remap = np.empty(len(sku_codes), dtype=np.int64)
    sk_remap[[sku_codes[s] for s in sk_ids]] = np.arange(len(sk_ids))
    store, sku = st_remap[store], sk_remap[sku]
    on_progress(0.45, "Sorting by store, SKU and date")
    order = np.lexsort((day, sku, store))
    store, sku, day = store[order], sku[order], day[order]
    meas = {f: v[order] for f, v in meas.items()}
    key = (store * 1_000_000 + sku) * 100_000 + (day - day.min())
    dup = np.r_[False, key[1:] == key[:-1]]
    if dup.any():
        warnings.append(f"Summed {int(dup.sum()):,} duplicate store/SKU/date rows.")
        starts = np.flatnonzero(~dup)
        for f in meas:
            if f in ("opening_stock", "counted_closing", "expected_closing", "on_promo"):
                meas[f] = meas[f][starts]
            else:
                meas[f] = np.add.reduceat(meas[f], starts)
        store, sku, day = store[starts], sku[starts], day[starts]
    if "expected_closing" not in meas:
        z = np.zeros(len(day), dtype=np.int64)
        g = lambda k: meas.get(k, z)  # noqa: E731
        meas["expected_closing"] = g("opening_stock") + g("received_units") + g("returned_units") + g("transfer_in_units") - g("sold_units") - g("transfer_out_units") + g("adjustment_units")
        warnings.append("Expected closing stock was derived from opening + received + returns + transfers - sold + adjustments.")
    d0 = int(day.min())
    dates = (np.arange(d0, int(day.max()) + 1).astype("datetime64[D]")).astype(str)
    cols = {"date_idx": (day - d0).astype(np.int16), "store_code": store.astype(np.int16), "sku_code": sku.astype(np.int16)}
    for f, v in meas.items():
        cols[f] = v.astype(synth.DAILY_SPECS[f])
    on_progress(0.5, "Writing the column store")
    colstore.write_columns(ds_dir / "daily", cols)
    # ---- dimension tables
    stores = pd.DataFrame({"store_id": st_ids})
    if files["stores"] is not None:
        s_in = pd.read_csv(files["stores"], dtype={"store_id": str})
        stores = stores.merge(s_in, on="store_id", how="left")
    stores["store_name"] = stores.get("store_name", stores["store_id"]).fillna(stores["store_id"]) if "store_name" in stores else stores["store_id"]
    for c, default in (("region", "Unknown"), ("warehouse_team", "All stores"), ("format", "unknown")):
        stores[c] = stores[c].fillna(default) if c in stores else default
    skus = pd.DataFrame({"sku_id": sk_ids})
    if files["skus"] is not None:
        k_in = pd.read_csv(files["skus"], dtype={"sku_id": str})
        skus = skus.merge(k_in, on="sku_id", how="left")
    elif sku_meta:
        skus["category"] = skus["sku_id"].map(lambda s: sku_meta.get(s, ("unknown", 1.0))[0])
        skus["unit_cost"] = skus["sku_id"].map(lambda s: sku_meta.get(s, ("unknown", 1.0))[1])
    if "category" not in skus:
        skus["category"] = "unknown"
        warnings.append("No category column: every SKU is 'unknown' (dashboards by category will be flat).")
    if "unit_cost" not in skus:
        skus["unit_cost"] = 1.0
        warnings.append("No unit cost: values at risk are in units (assumed £1 each).")
    skus["category"] = skus["category"].fillna("unknown").astype(str).str.lower()
    skus["unit_cost"] = pd.to_numeric(skus["unit_cost"], errors="coerce").fillna(1.0)
    if "sku_name" not in skus:
        skus["sku_name"] = skus["sku_id"]
    skus["sku_name"] = skus["sku_name"].fillna(skus["sku_id"])
    st_index = {s: i for i, s in enumerate(st_ids)}
    sk_index = {s: i for i, s in enumerate(sk_ids)}
    # ---- loss-prevention flags and (for our own exports) the answer key
    lp = pd.DataFrame(columns=["flag_id", "date", "store_id", "sku_id", "date_idx", "store_code", "sku_code", "flag_type", "source", "confirmed", "loss_value_gbp"])
    if files["lp_flags"] is not None:
        f_in = pd.read_csv(files["lp_flags"], dtype={"store_id": str, "sku_id": str})
        f_in = f_in[f_in["store_id"].isin(st_index) & f_in["sku_id"].isin(sk_index)].copy()
        f_in["store_code"] = f_in["store_id"].map(st_index)
        f_in["sku_code"] = f_in["sku_id"].map(sk_index)
        f_in["date_idx"] = (pd.to_datetime(f_in["date"]).to_numpy().astype("datetime64[D]").astype(np.int64) - d0)
        f_in = f_in[(f_in["date_idx"] >= 0) & (f_in["date_idx"] < len(dates))]
        for c, default in (("flag_type", "theft"), ("source", "unknown"), ("confirmed", True), ("loss_value_gbp", 0.0)):
            if c not in f_in:
                f_in[c] = default
        if "flag_id" not in f_in:
            f_in["flag_id"] = [f"LP{i + 1:05d}" for i in range(len(f_in))]
        lp = f_in[list(lp.columns)]
    if files["answer_key"] is not None:
        on_progress(0.55, "Attaching the answer key")
        ak = pd.read_csv(files["answer_key"], dtype={"store_id": str, "sku_id": str})
        ak = ak[ak["store_id"].isin(st_index) & ak["sku_id"].isin(sk_index)]
        akey = (ak["store_id"].map(st_index).to_numpy() * 1_000_000 + ak["sku_id"].map(sk_index).to_numpy()) * 100_000 + (pd.to_datetime(ak["date"]).to_numpy().astype("datetime64[D]").astype(np.int64) - d0)
        rkey = (store * 1_000_000 + sku) * 100_000 + (day - d0)
        pos = np.searchsorted(rkey, akey)
        good = (pos < len(rkey)) & (rkey[np.minimum(pos, len(rkey) - 1)] == akey)
        tcode = {n: i for i, n in enumerate(config.ANOMALY_TYPES)}
        truth = {k: np.zeros(len(rkey), dtype=v) for k, v in synth.TRUTH_SPECS.items()}
        truth["truth_type"][pos[good]] = ak["truth_type"].map(lambda t: tcode.get(str(t), 0)).to_numpy()[good]
        truth["truth_incident"][pos[good]] = ak["truth_incident"].to_numpy()[good]
        truth["truth_loss_units"][pos[good]] = ak["truth_loss_units"].to_numpy()[good]
        colstore.write_columns(ds_dir / "truth", truth)
    params: dict[str, Any] = {"source_file": daily_path.name}
    if files["metadata"] is not None:
        try:
            md = json.loads(Path(files["metadata"]).read_text(encoding="utf-8"))
            params["imported_from"] = md.get("name")
            name = name or md.get("name")
        except ValueError:
            pass
    det = Detection(column_map=cmap, missing_optional=missing, source_file=daily_path.name)
    meta = datasets.finalize(
        ds_id, name or f"Imported {daily_path.stem}", "upload", stores, skus, dates, lp, params, det, warnings,
        on_progress=lambda f, m: on_progress(0.55 + 0.42 * f, m),
    )
    return meta  # raw files stay in raw/ so the column mapping can be changed later


def as_text(buf: bytes) -> io.StringIO:
    return io.StringIO(buf.decode("utf-8-sig"))
