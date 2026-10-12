"""Investigation planner: turn investigator hours into a ranked work list with an expected return.

For each alert i:
    cash_i = value_at_risk_i x cash_share(type_i)   (book-keeping errors are corrected, not recovered as money)
    V_i  = cash_i x recovery_rate                                  (what investigating recovers now)
         + cash_i x persist(type_i) x horizon_days / 28            (a similar loss it stops from happening again)
    EV_i = P(true anomaly)_i x V_i
    cost = minutes(type_i) / 60 x hourly_cost
Alerts are ranked by EV per hour and taken until the hours run out. The naive comparison spends the same hours
in order of raw value at risk, ignoring how likely each alert is to be real.
"""
from __future__ import annotations

import csv
import io
import zipfile
from typing import Any, Iterator

import numpy as np
import pandas as pd

from app import config
from app.schemas import InvestigationPlan, PlanBreakdown, PlanCurvePoint, PlanRequest, PlanRow
from app.services import storage, triage

WORKLIST_COLUMNS = ["priority", "team", "alert_id", "store_id", "store_name", "sku_id", "sku_name", "category", "start_date", "end_date", "likely_type", "severity", "p_true", "value_at_risk_gbp", "expected_value_gbp", "minutes", "reason_1", "reason_2", "reason_3"]


def _frame(req: PlanRequest) -> tuple[pd.DataFrame, str, str]:
    rd = storage.load_run(req.run_id)
    df = rd.incidents.copy()
    meta = storage.get_model(rd.run.model_id)
    cal_src = meta.calibration.source if meta else "prior"
    if not len(df):
        return df, rd.run.model_name, cal_src
    if not req.include_reviewed:
        done = triage.latest(rd.run.dataset_id)
        df = df[~df["alert_key"].isin(done)]
    if req.severities:
        df = df[df["severity"].isin(req.severities)]
    if req.teams:
        df = df[df["warehouse_team"].isin(req.teams)]
    minutes = {**config.MINUTES_BY_TYPE, **(req.minutes_by_type or {})}
    persist = {**config.PERSIST_BY_TYPE, **(req.persist_by_type or {})}
    df["minutes"] = df["likely_type"].map(lambda t: float(minutes.get(t, minutes["unclear"])))
    cash = df["likely_type"].map(lambda t: float(config.CASH_SHARE_BY_TYPE.get(t, 0.5)))
    at_risk = df["value_at_risk_gbp"] * cash
    v = at_risk * req.recovery_rate + at_risk * (req.horizon_days / 28.0) * df["likely_type"].map(lambda t: float(persist.get(t, persist["unclear"])))
    df["expected_value_gbp"] = (df["p_true"] * v).round(2)
    df["cost_gbp"] = df["minutes"] / 60 * req.hourly_cost
    df["ev_per_hour"] = df["expected_value_gbp"] / (df["minutes"] / 60)
    df = df.sort_values(["ev_per_hour", "value_at_risk_gbp"], ascending=False).reset_index(drop=True)
    return df, rd.run.model_name, cal_src


def rank_by_alert(run_id: str) -> dict[str, int]:
    """alert_id -> position in the planner's order (expected recovery per investigator hour), reviewed alerts included."""
    df, _, _ = _frame(PlanRequest(run_id=run_id, include_reviewed=True))
    return {str(a): i for i, a in enumerate(df["alert_id"])} if len(df) else {}


def top_alert_ids(run_id: str, n: int = 5) -> list[str]:
    """The open alerts the planner would work first (expected recovery per investigator hour, default assumptions)."""
    df, _, _ = _frame(PlanRequest(run_id=run_id))
    return [str(a) for a in df["alert_id"].head(n)] if len(df) else []


def _take(df: pd.DataFrame, hours: float) -> pd.DataFrame:
    cum = (df["minutes"] / 60).cumsum()
    return df[cum <= hours + 1e-9]


def plan(req: PlanRequest) -> InvestigationPlan:
    df, model_name, cal_src = _frame(req)
    if not len(df):
        return InvestigationPlan(run_id=req.run_id, model_name=model_name, hours=req.hours, hourly_cost=req.hourly_cost, recovery_rate=req.recovery_rate, horizon_days=req.horizon_days, n_candidates=0, n_selected=0, hours_used=0, cost=0, expected_recovered=0, net_benefit=0, roi=0, breakeven_hours=None, naive_expected=0, calibration_source=cal_src, by_team=[], by_type=[], by_severity=[], curve=[], top_rows=[], explanation="No open alerts to plan.")
    sel = _take(df, req.hours)
    naive = df.sort_values("value_at_risk_gbp", ascending=False)
    naive_sel = _take(naive, req.hours)
    cost = float(sel["cost_gbp"].sum())
    ev = float(sel["expected_value_gbp"].sum())
    hours_used = float((sel["minutes"] / 60).sum())
    # breakeven: the point where one more investigation is expected to return less than it costs
    marginal = df["expected_value_gbp"] - df["cost_gbp"]
    below = np.flatnonzero(marginal.to_numpy() < 0)
    breakeven = float((df["minutes"].iloc[: below[0]] / 60).sum()) if len(below) else None
    pts = []
    max_h = max(req.hours * 2, 1.0)
    cum_h = (df["minutes"] / 60).cumsum().to_numpy()
    cum_ev = df["expected_value_gbp"].cumsum().to_numpy()
    cum_cost = df["cost_gbp"].cumsum().to_numpy()
    n_cum_h = (naive["minutes"] / 60).cumsum().to_numpy()
    n_cum_ev = naive["expected_value_gbp"].cumsum().to_numpy()
    for h in np.linspace(0, max_h, config.PLANNER_CURVE_POINTS):
        k = int(np.searchsorted(cum_h, h + 1e-9, side="right"))
        nk = int(np.searchsorted(n_cum_h, h + 1e-9, side="right"))
        e = float(cum_ev[k - 1]) if k else 0.0
        c = float(cum_cost[k - 1]) if k else 0.0
        pts.append(PlanCurvePoint(hours=round(float(h), 1), alerts=k, expected_recovered=round(e, 2), cost=round(c, 2), roi=round((e - c) / c, 3) if c else 0.0, naive_expected=round(float(n_cum_ev[nk - 1]) if nk else 0.0, 2)))

    def breakdown(col: str) -> list[PlanBreakdown]:
        if not len(sel):
            return []
        g = sel.groupby(col).agg(alerts=("alert_id", "size"), minutes=("minutes", "sum"), ev=("expected_value_gbp", "sum"), var=("value_at_risk_gbp", "sum")).reset_index().sort_values("ev", ascending=False)
        return [PlanBreakdown(key=str(r[col]), alerts=int(r["alerts"]), hours=round(float(r["minutes"]) / 60, 1), expected_recovered=round(float(r["ev"]), 2), value_at_risk_gbp=round(float(r["var"]), 2)) for _, r in g.iterrows()]

    top = [PlanRow(priority=i + 1, alert_id=r["alert_id"], team=str(r["warehouse_team"]), store_id=str(r["store_id"]), store_name=r["store_name"], sku_id=str(r["sku_id"]), sku_name=r["sku_name"], category=r["category"], start_date=r["start_date"], likely_type=r["likely_type"], severity=r["severity"], p_true=float(r["p_true"]), value_at_risk_gbp=float(r["value_at_risk_gbp"]), expected_value_gbp=float(r["expected_value_gbp"]), minutes=float(r["minutes"])) for i, r in enumerate(sel.head(config.PLANNER_TOP_ROWS).to_dict("records"))]
    naive_ev = float(naive_sel["expected_value_gbp"].sum())
    roi = (ev - cost) / cost if cost else 0.0
    lift = f"{ev / naive_ev:.1f}x" if naive_ev > 0 else "n/a"
    expl = (
        f"{req.hours:.0f} investigator hours cover {len(sel):,} of {len(df):,} open alerts. Expected recovery £{ev:,.0f} for £{cost:,.0f} of time "
        f"(return {roi:.1f}x on cost). Working down the list by raw £ at risk instead would recover about £{naive_ev:,.0f}, so the ranking is worth {lift} that. "
        f"Estimates assume {req.recovery_rate:.0%} of the money at risk is recovered (book-keeping errors count only a small share), and P(true anomaly) from {cal_src.replace('_', ' ')}."
    )
    return InvestigationPlan(
        run_id=req.run_id, model_name=model_name, hours=req.hours, hourly_cost=req.hourly_cost, recovery_rate=req.recovery_rate, horizon_days=req.horizon_days,
        n_candidates=int(len(df)), n_selected=int(len(sel)), hours_used=round(hours_used, 1), cost=round(cost, 2), expected_recovered=round(ev, 2), net_benefit=round(ev - cost, 2),
        roi=round(roi, 3), breakeven_hours=round(breakeven, 1) if breakeven is not None else None, naive_expected=round(naive_ev, 2), calibration_source=cal_src,
        by_team=breakdown("warehouse_team"), by_type=breakdown("likely_type"), by_severity=breakdown("severity"), curve=pts, top_rows=top, explanation=expl,
    )


def _rows(sel: pd.DataFrame) -> Iterator[list[Any]]:
    for i, r in enumerate(sel.to_dict("records")):
        reasons = [x for x in str(r.get("reasons", "")).split(" || ") if x] + ["", "", ""]
        yield [i + 1, r["warehouse_team"], r["alert_id"], r["store_id"], r["store_name"], r["sku_id"], r["sku_name"], r["category"], r["start_date"], r["end_date"], r["likely_type"], r["severity"], r["p_true"], r["value_at_risk_gbp"], r["expected_value_gbp"], r["minutes"], *reasons[:3]]


def worklist_csv(req: PlanRequest, team: str | None = None) -> str:
    df, _, _ = _frame(req)
    sel = _take(df, req.hours) if len(df) else df
    if team and len(sel):
        sel = sel[sel["warehouse_team"] == team]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(WORKLIST_COLUMNS)
    if len(sel):
        w.writerows(_rows(sel))
    return buf.getvalue()


def worklist_zip(req: PlanRequest) -> bytes:
    df, _, _ = _frame(req)
    sel = _take(df, req.hours) if len(df) else df
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        teams = sorted(sel["warehouse_team"].unique()) if len(sel) else []
        for t in teams:
            sub = sel[sel["warehouse_team"] == t]
            s = io.StringIO()
            w = csv.writer(s)
            w.writerow(WORKLIST_COLUMNS)
            w.writerows(_rows(sub))
            zf.writestr(f"worklist_{storage.safe_name(str(t))}.csv", s.getvalue())
        zf.writestr("README.txt", f"Investigation work lists for run {req.run_id}: {req.hours:.0f} hours, one CSV per warehouse team, highest expected recovery per hour first.\n")
    return buf.getvalue()
