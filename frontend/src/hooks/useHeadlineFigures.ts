import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../context";
import type { Alert, Dashboard, InvestigationPlan, ModelMeta } from "../types";

/** Live figures from whatever is loaded, with illustrative fallbacks labelled as such. */
export function useHeadlineFigures() {
  const { datasets, models, runs, config } = useApp();
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [plan, setPlan] = useState<InvestigationPlan | null>(null);
  const [top, setTop] = useState<Alert | null>(null);
  const [rr, setRr] = useState<ModelMeta | null>(null);
  const run = runs.find((r) => r.model_in_use) ?? runs[0] ?? null;
  useEffect(() => {
    if (!run) {
      setDash(null);
      setPlan(null);
      setTop(null);
      return;
    }
    let stop = false;
    api.runs.dashboard(run.run_id).then((d) => !stop && setDash(d)).catch(() => undefined);
    const p = config.planner_defaults;
    api.planner.plan({ run_id: run.run_id, hours: p.hours, hourly_cost: p.hourly_cost, recovery_rate: p.recovery_rate, horizon_days: p.horizon_days }).then((x) => !stop && setPlan(x)).catch(() => undefined);
    api.runs.alerts(run.run_id, { severity: ["critical"], sort: "plan", limit: 1 }).then((x) => !stop && setTop(x.alerts[0] ?? null)).catch(() => undefined);
    return () => {
      stop = true;
    };
  }, [run?.run_id, config.planner_defaults]);
  const reranker = models.find((m) => m.key === "reranker") ?? null;
  useEffect(() => {
    if (!reranker) return setRr(null);
    api.models.get(reranker.model_id).then(setRr).catch(() => setRr(null));
  }, [reranker?.model_id]);
  const ds = datasets[0] ?? null;
  const dsModels = models.filter((m) => m.dataset_id === (ds?.id ?? "") && m.key !== "reranker");
  const latestJob = dsModels[0]?.job_id;
  const runModels = dsModels.filter((m) => m.job_id === latestJob);
  const ap = Object.fromEntries(runModels.map((m) => [m.key, m.metrics.average_precision ?? 0]));
  const live = !!(ds && runModels.length && dash);
  return {
    live,
    rows: ds?.n_rows ?? 5_000_000,
    stores: ds?.n_stores ?? 80,
    skus: ds?.n_skus ?? 500,
    days: ds?.n_days ?? 125,
    incidentsHidden: ds?.n_incidents ?? 5600,
    ap: Object.keys(ap).length ? ap : { zscore: 0.26, iforest: 0.45, lof: 0.29, autoencoder: 0.26 },
    alerts: dash?.run.kpis.incidents ?? 25_000,
    critical: dash?.run.kpis.by_severity.critical ?? 1700,
    valueAtRisk: dash?.run.kpis.value_at_risk_gbp ?? 560_000,
    recall: dash?.run.evaluation?.incident_recall ?? 0.54,
    topStores: dash?.top_stores.slice(0, 3) ?? [],
    topCats: dash?.by_category.slice(0, 3) ?? [],
    plan,
    top,
    fe: rr?.feedback_eval ?? null,
    model: dash?.run.model_label ?? "Isolation Forest",
    runId: run?.run_id ?? null,
    dash,
  };
}
