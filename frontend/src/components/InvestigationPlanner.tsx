import { useEffect, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { InvestigationPlan } from "../types";
import { HoursCurveChart, MetricBarChart, TYPE_COLOR } from "./Charts";
import { EmptyState, InvestigationArt } from "./Illustrations";
import { Help, SeverityChip, Spinner, StatCard, TypeChip } from "./Layout";
import { TechnicalDetails } from "./TechnicalDetails";
import { gbp, num, SOURCE_LABEL, TYPE_LABEL } from "../utils";

export function InvestigationPlanner({ runId, simple = false }: { runId: string; simple?: boolean }) {
  const { config, toast, openDrill } = useApp();
  const d = config.planner_defaults;
  const [hours, setHours] = useState(d.hours);
  const [cost, setCost] = useState(d.hourly_cost);
  const [recovery, setRecovery] = useState(d.recovery_rate);
  const [horizon, setHorizon] = useState(d.horizon_days);
  const [onlyHigh, setOnlyHigh] = useState(false);
  const [plan, setPlan] = useState<InvestigationPlan | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setHours(d.hours);
    setCost(d.hourly_cost);
    setRecovery(d.recovery_rate);
    setHorizon(d.horizon_days);
  }, [d.hours, d.hourly_cost, d.recovery_rate, d.horizon_days]);
  useEffect(() => {
    let stop = false;
    setLoading(true);
    const t = setTimeout(() => {
      api.planner
        .plan({ run_id: runId, hours, hourly_cost: cost, recovery_rate: recovery, horizon_days: horizon, severities: onlyHigh ? ["critical", "high"] : null })
        .then((p) => !stop && setPlan(p))
        .catch((e) => toast(errorMessage(e), "error"))
        .finally(() => !stop && setLoading(false));
    }, 250);
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [runId, hours, cost, recovery, horizon, onlyHigh, toast]);
  const params = { hours, hourly_cost: cost, recovery_rate: recovery, horizon_days: horizon, severities: onlyHigh ? (["critical", "high"] as ("critical" | "high")[]) : null };
  return (
    <div className="stack">
      <div className="grid grid-side">
        <div className="card">
          <div className="card-title">
            <h2>Investigator time</h2>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            <label className="field">
              <span>
                Hours available this week · <b>{num.format(hours)} h</b>
              </span>
              <input type="range" min={8} max={1000} step={4} value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Investigator hours" />
            </label>
            {simple ? (
              <p className="small muted" style={{ margin: 0 }}>
                At {gbp.format(cost)} an hour. Slide to see what more or fewer investigator hours would recover.
              </p>
            ) : (<>
            <label className="field">
              <span>
                Cost of one hour · <b>{gbp.format(cost)}</b>
              </span>
              <input type="range" min={10} max={80} step={1} value={cost} onChange={(e) => setCost(Number(e.target.value))} aria-label="Hourly cost" />
            </label>
            <label className="check small">
              <input type="checkbox" checked={onlyHigh} onChange={(e) => setOnlyHigh(e.target.checked)} /> Only critical and high alerts
            </label>
            <TechnicalDetails title="Assumptions">
              <label className="field">
                <span>
                  Recovered when a real problem is investigated · {Math.round(recovery * 100)}% <Help text="Share of the money at risk that action gets back or stops losing (stock found, supplier credited, loss stopped)." />
                </span>
                <input type="range" min={0.05} max={1} step={0.05} value={recovery} onChange={(e) => setRecovery(Number(e.target.value))} />
              </label>
              <label className="field">
                <span>
                  Days of further loss prevented · {horizon} <Help text="Acting now stops a continuing problem from running on; book-keeping errors do not continue." />
                </span>
                <input type="range" min={0} max={90} step={1} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
              </label>
              <div className="small muted">
                Minutes per investigation by likely type: {Object.entries(config.minutes_by_type).map(([t, m]) => `${TYPE_LABEL[t] ?? t} ${m}`).join(" · ")}. Book-keeping errors (miscounts, typing) count only a small share of their value because fixing a record does not bring money back. P(true) comes from {plan ? SOURCE_LABEL[plan.calibration_source] : "the model"}.
              </div>
            </TechnicalDetails>
            </>)}
            {plan && !simple ? (
              <div className="row">
                <a className="btn primary" href={api.planner.worklistZipUrl(runId, params)}>
                  Work lists per team (ZIP)
                </a>
                <a className="btn" href={api.planner.worklistCsvUrl(runId, params)}>
                  One CSV
                </a>
              </div>
            ) : null}
          </div>
        </div>
        <div className="stack">
          {!plan ? (
            <Spinner />
          ) : plan.n_candidates === 0 ? (
            <div className="card">
              <EmptyState art={<InvestigationArt />}>
                <b>No open alerts to plan.</b>
                <div className="muted">Everything in this run has been reviewed, or the filters exclude it.</div>
              </EmptyState>
            </div>
          ) : (
            <>
              <div className="grid grid-4">
                <StatCard label="Alerts worked" value={num.format(plan.n_selected)} sub={`of ${num.format(plan.n_candidates)} open · ${plan.hours_used.toFixed(0)} h used`} />
                <StatCard label="Expected recovery" value={gbp.format(plan.expected_recovered)} sub={`for ${gbp.format(plan.cost)} of investigator time`} />
                <StatCard label="Return on cost" value={`${plan.roi.toFixed(1)}x`} sub={`net ${gbp.format(plan.net_benefit)}`} />
                <StatCard label="Worth it up to" value={plan.breakeven_hours !== null ? `${num.format(plan.breakeven_hours)} h` : "all alerts"} sub="after that an hour returns less than it costs" />
              </div>
              <div className="card">
                <div className="card-title">
                  <h3>What more hours buy</h3>
                  {loading ? <Spinner /> : null}
                </div>
                <HoursCurveChart curve={plan.curve} hours={hours} />
                <p className="small muted">
                  {simple
                    ? `Working alerts in the model's order recovers more than spending the same hours on the biggest £ first. Estimates assume ${Math.round(recovery * 100)}% of the money at risk is recovered when a problem is real.`
                    : plan.explanation}
                </p>
              </div>
            </>
          )}
        </div>
      </div>
      {plan && plan.n_selected ? (
        <>
          {simple ? null : (
          <div className="grid grid-2">
            <div className="card">
              <div className="card-title">
                <h3>Expected recovery by team</h3>
              </div>
              <MetricBarChart rows={plan.by_team.map((b) => ({ label: `${b.key} (${b.alerts})`, value: b.expected_recovered }))} metric="Expected recovery" format={(v) => gbp.format(v)} />
            </div>
            <div className="card">
              <div className="card-title">
                <h3>By likely type</h3>
              </div>
              <MetricBarChart rows={plan.by_type.map((b) => ({ label: `${TYPE_LABEL[b.key] ?? b.key} (${b.alerts})`, value: b.expected_recovered, color: TYPE_COLOR[b.key] }))} metric="Expected recovery" format={(v) => gbp.format(v)} />
            </div>
          </div>
          )}
          <div className="card">
            <div className="card-title">
              <h3>{simple ? "Work these first" : `The work list (top ${plan.top_rows.length})`}</h3>
              {simple ? <span className="small muted">click a row for its stock story</span> : null}
            </div>
            <div className="table-wrap" style={{ maxHeight: 460 }}>
              <table className="data">
                <thead>
                  <tr>
                    <th className="num">#</th>
                    <th>Team</th>
                    <th>Store · item</th>
                    {simple ? null : <th>From</th>}
                    <th>Likely type</th>
                    <th>Severity</th>
                    {simple ? null : <th className="num">P(true)</th>}
                    <th className="num">£ at risk</th>
                    <th className="num">{simple ? "Expected back" : "Expected"}</th>
                    {simple ? null : <th className="num">Minutes</th>}
                  </tr>
                </thead>
                <tbody>
                  {(simple ? plan.top_rows.slice(0, 10) : plan.top_rows).map((r) => (
                    <tr key={r.alert_id} className="clickable" onClick={() => openDrill(r.store_id, r.sku_id, r.alert_id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && openDrill(r.store_id, r.sku_id, r.alert_id)}>
                      <td className="num">{r.priority}</td>
                      <td className="small">{r.team}</td>
                      <td>
                        {r.store_name}
                        <div className="small muted">
                          {r.sku_name}
                          {simple ? null : <> · <span className="mono">{r.alert_id}</span></>}
                        </div>
                      </td>
                      {simple ? null : <td className="small">{r.start_date}</td>}
                      <td>
                        <TypeChip type={r.likely_type} />
                      </td>
                      <td>
                        <SeverityChip severity={r.severity} />
                      </td>
                      {simple ? null : <td className="num">{Math.round(r.p_true * 100)}%</td>}
                      <td className="num">{gbp.format(r.value_at_risk_gbp)}</td>
                      <td className="num">{gbp.format(r.expected_value_gbp)}</td>
                      {simple ? null : <td className="num">{r.minutes}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
