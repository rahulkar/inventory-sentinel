import { ArrowRight, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { SopChecklist } from "./SopChecklist";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { SeriesResponse } from "../types";
import { SeriesChart } from "./Charts";
import { SeverityChip, Spinner, TypeChip } from "./Layout";
import { confidenceWord, gbp, num, TYPE_LABEL } from "../utils";

const SEV_RANK: Record<string, number> = { critical: 3, high: 2, medium: 1 };

/** Executive mode: one item's stock story in a side drawer (the analyst view uses the Drill-down tab instead). */
export function AlertDrawer() {
  const { drawer, openDrawer, runs, selectedRunId, toast, setPage, setSelectedAlertId } = useApp();
  const runId = selectedRunId ?? runs[0]?.run_id ?? null;
  const [s, setS] = useState<SeriesResponse | null>(null);

  useEffect(() => {
    setS(null);
    if (!drawer || !runId) return;
    let stop = false;
    api.runs
      .series(runId, drawer.storeId, drawer.skuId)
      .then((x) => !stop && setS(x))
      .catch((e) => toast(errorMessage(e), "error"));
    return () => {
      stop = true;
    };
  }, [drawer, runId, toast]);

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && openDrawer(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer, openDrawer]);

  const alert = useMemo(() => {
    if (!s) return null;
    return s.alerts.find((a) => a.alert_id === drawer?.alertId) ?? [...s.alerts].sort((a, b) => (SEV_RANK[b.severity] ?? 0) - (SEV_RANK[a.severity] ?? 0) || b.value_at_risk_gbp - a.value_at_risk_gbp)[0] ?? null;
  }, [s, drawer?.alertId]);

  if (!drawer) return null;
  return (
    <>
      <div className="drawer-scrim" onClick={() => openDrawer(null)} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Stock story">
        <div className="card-title">
          <h2>{s ? `${s.store_name} · ${s.sku_name}` : "Stock story"}</h2>
          <button className="btn sm link" onClick={() => openDrawer(null)} aria-label="Close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {!s ? (
          <Spinner />
        ) : (
          <div className="stack" style={{ gap: 14 }}>
            {alert ? (
              <>
                <div className="row" style={{ gap: 6 }}>
                  <SeverityChip severity={alert.severity} />
                  <TypeChip type={alert.likely_type} />
                  <span className="chip neutral">{confidenceWord(alert.p_true)} confidence</span>
                </div>
                <div className="drawer-facts">
                  <div>
                    <b>{gbp.format(alert.value_at_risk_gbp)}</b>
                    <span>at risk ({num.format(alert.units_at_risk)} units)</span>
                  </div>
                  <div>
                    <b>{alert.n_days === 1 ? alert.start_date : `${alert.n_days} days`}</b>
                    <span>{alert.n_days === 1 ? "one day" : `${alert.start_date} to ${alert.end_date}`}</span>
                  </div>
                  <div>
                    <b>{alert.warehouse_team}</b>
                    <span>team to send</span>
                  </div>
                </div>
                <div>
                  <h3 style={{ margin: "0 0 4px" }}>Why it was flagged</h3>
                  <ul className="reasons">
                    {alert.reasons.slice(0, 3).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                  <p className="small muted" style={{ margin: "6px 0 0" }}>
                    The pattern is consistent with {TYPE_LABEL[alert.likely_type]?.toLowerCase() ?? "a problem"}; an investigation confirms what happened.
                  </p>
                </div>
              </>
            ) : (
              <p className="muted">No alerts on this item in the current run.</p>
            )}
            {alert && runId ? (
              <div>
                <h3 style={{ margin: "0 0 4px" }}>What to do</h3>
                <SopChecklist runId={runId} alertId={alert.alert_id} compact />
              </div>
            ) : null}
            <div>
              <h3 style={{ margin: "0 0 4px" }}>Expected against counted stock</h3>
              <SeriesChart points={s.points} height={220} />
              <p className="small muted" style={{ margin: "4px 0 0" }}>Shaded days were flagged. The gap is stock the books expect but the count did not find.</p>
            </div>
            {alert ? (
              <div className="row">
                <button
                  className="btn"
                  onClick={() => {
                    setSelectedAlertId(alert.alert_id);
                    openDrawer(null);
                    setPage("alerts");
                  }}
                >
                  Record the outcome <ArrowRight size={16} aria-hidden="true" />
                </button>
              </div>
            ) : null}
          </div>
        )}
      </aside>
    </>
  );
}
