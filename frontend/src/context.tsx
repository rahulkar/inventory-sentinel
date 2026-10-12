import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import type { AppConfig, DatasetMeta, DetectionRunSummary, Job, ModelMeta, ModelSpec, ModelSummary } from "./types";
import { defaultConfig, isTerminal } from "./utils";

export type Page = "overview" | "story" | "data" | "train" | "act" | "models" | "experiments" | "assistant" | "settings" | "alerts" | "plan";
export type Area = "business" | "analyst";
/** exec = lean CIO/CTO view (Overview, Alerts, Plan, Story); analyst = every page and tab. */
export type Mode = "exec" | "analyst";
export const EXEC_PAGES: Page[] = ["overview", "alerts", "plan", "story", "assistant"];
export interface Drawer {
  storeId: string;
  skuId: string;
  alertId?: string | null;
}

const MODE_KEY = "sentinel.mode";
function loadMode(): Mode {
  try {
    return window.localStorage.getItem(MODE_KEY) === "analyst" ? "analyst" : "exec";
  } catch {
    return "exec";
  }
}
export type ActTab = "alerts" | "dashboard" | "planner" | "drill" | "triage";

export interface Toast {
  id: number;
  kind: "info" | "success" | "error";
  message: string;
}

interface AppState {
  page: Page;
  area: Area;
  setPage: (p: Page) => void;
  mode: Mode;
  setMode: (m: Mode) => void;
  drawer: Drawer | null;
  openDrawer: (d: Drawer | null) => void;
  config: AppConfig;
  datasets: DatasetMeta[];
  models: ModelSummary[];
  activeModel: ModelMeta | null;
  availableModels: ModelSpec[];
  runs: DetectionRunSummary[];
  selectedDatasetId: string | null;
  setSelectedDatasetId: (id: string | null) => void;
  selectedRunId: string | null;
  setSelectedRunId: (id: string | null) => void;
  selectedAlertId: string | null;
  setSelectedAlertId: (id: string | null) => void;
  drill: { storeId: string; skuId: string } | null;
  openDrill: (storeId: string, skuId: string, alertId?: string | null) => void;
  actTab: ActTab;
  setActTab: (t: ActTab) => void;
  refreshDatasets: () => Promise<void>;
  refreshModels: () => Promise<void>;
  refreshRuns: () => Promise<void>;
  activateModel: (id: string) => Promise<void>;
  deleteModel: (id: string) => Promise<void>;
  jobs: Record<string, Job>;
  activeJobs: Job[];
  watchJob: (job: Job) => void;
  cancelJob: (id: string) => Promise<void>;
  toast: (message: string, kind?: Toast["kind"]) => void;
  toasts: Toast[];
  backendOk: boolean | null;
}

const Ctx = createContext<AppState | null>(null);

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

const JOB_TITLES: Record<string, string> = {
  generate: "Dataset generated",
  upload: "Dataset imported",
  train: "Training finished",
  detect: "Detection finished",
  retrain: "Feedback re-ranker trained",
  export: "Export ready",
};

export function AppProvider({ children }: { children: ReactNode }) {
  const [page, setPageRaw] = useState<Page>("overview");
  const [mode, setModeRaw] = useState<Mode>(loadMode);
  const [drawer, setDrawer] = useState<Drawer | null>(null);
  const [config, setConfig] = useState<AppConfig>(defaultConfig());
  const [datasets, setDatasets] = useState<DatasetMeta[]>([]);
  const [models, setModels] = useState<ModelSummary[]>([]);
  const [activeModel, setActiveModel] = useState<ModelMeta | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelSpec[]>([]);
  const [runs, setRuns] = useState<DetectionRunSummary[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [drill, setDrill] = useState<{ storeId: string; skuId: string } | null>(null);
  const [actTab, setActTab] = useState<ActTab>("alerts");
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const toastId = useRef(0);
  const notified = useRef<Set<string>>(new Set());

  const toast = useCallback((message: string, kind: Toast["kind"] = "info") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 8000 : 4500);
  }, []);

  const refreshDatasets = useCallback(async () => {
    const list = await api.datasets.list();
    setDatasets(list);
    setSelectedDatasetId((cur) => (cur && list.some((d) => d.id === cur) ? cur : list[0]?.id ?? null));
  }, []);

  const refreshModels = useCallback(async () => {
    const [list, active] = await Promise.all([api.models.list(), api.models.active()]);
    setModels(list);
    setActiveModel(active);
  }, []);

  const refreshRuns = useCallback(async () => {
    const list = await api.runs.list();
    setRuns(list);
    setSelectedRunId((cur) => (cur && list.some((r) => r.run_id === cur) ? cur : list[0]?.run_id ?? null));
  }, []);

  const setPage = useCallback((p: Page) => {
    setDrawer(null);
    setPageRaw(p);
  }, []);

  const modeRef = useRef(mode);
  modeRef.current = mode;
  const actTabRef = useRef(actTab);
  actTabRef.current = actTab;
  const pageRef = useRef(page);
  pageRef.current = page;

  // Switching mode keeps you on the equivalent screen: exec Alerts/Plan <-> Act tabs.
  const setMode = useCallback((m: Mode) => {
    setModeRaw(m);
    try {
      window.localStorage.setItem(MODE_KEY, m);
    } catch {
      /* private window: the choice lasts for this tab only */
    }
    setDrawer(null);
    const cur = pageRef.current;
    if (m === "analyst") {
      if (cur === "alerts" || cur === "plan") {
        setActTab(cur === "alerts" ? "alerts" : "planner");
        setPageRaw("act");
      }
    } else if (cur === "act") {
      setPageRaw(actTabRef.current === "planner" ? "plan" : "alerts");
    } else if (!EXEC_PAGES.includes(cur)) {
      setPageRaw("overview");
    }
  }, []);

  // In executive mode the stock story opens in a side drawer instead of the Drill-down tab.
  const openDrill = useCallback((storeId: string, skuId: string, alertId?: string | null) => {
    if (modeRef.current === "exec") {
      setDrawer({ storeId, skuId, alertId: alertId ?? null });
      return;
    }
    setDrill({ storeId, skuId });
    setActTab("drill");
    setPageRaw("act");
  }, []);

  const activateModel = useCallback(
    async (id: string) => {
      await api.models.activate(id);
      await refreshModels();
      toast("This model is now used for new detection runs", "success");
    },
    [refreshModels, toast],
  );

  const deleteModel = useCallback(
    async (id: string) => {
      await api.models.delete(id);
      await refreshModels();
      toast("Model deleted", "info");
    },
    [refreshModels, toast],
  );

  const watchJob = useCallback((job: Job) => {
    setJobs((j) => ({ ...j, [job.job_id]: job }));
  }, []);

  const cancelJob = useCallback(
    async (id: string) => {
      await api.jobs.cancel(id);
      toast("Cancelling…");
    },
    [toast],
  );

  // Initial load: config, registry, datasets, models, results, and any jobs already running on the server.
  useEffect(() => {
    (async () => {
      try {
        await api.health();
        setBackendOk(true);
        const [cfg, specs, active] = await Promise.all([api.config(), api.models.available(), api.jobs.list(true)]);
        setConfig(cfg);
        setAvailableModels(specs);
        setJobs(Object.fromEntries(active.map((j) => [j.job_id, j])));
        await Promise.all([refreshDatasets(), refreshModels(), refreshRuns()]);
      } catch (e) {
        setBackendOk(false);
        toast(`Cannot reach the API: ${errorMessage(e)}`, "error");
      }
    })();
  }, [refreshDatasets, refreshModels, refreshRuns, toast]);

  // Poll every watched job that is still active; refresh lists when one finishes.
  const activeIds = useMemo(
    () =>
      Object.values(jobs)
        .filter((j) => !isTerminal(j.status))
        .map((j) => j.job_id)
        .sort()
        .join(","),
    [jobs],
  );
  useEffect(() => {
    if (!activeIds) return;
    const ids = activeIds.split(",");
    let stopped = false;
    const tick = async () => {
      for (const id of ids) {
        try {
          const j = await api.jobs.get(id);
          if (stopped) return;
          setJobs((cur) => ({ ...cur, [id]: j }));
          if (isTerminal(j.status) && !notified.current.has(id)) {
            notified.current.add(id);
            if (j.status === "done") {
              toast(`${JOB_TITLES[j.type] ?? "Job finished"}: ${j.title}`, "success");
              if (j.type === "generate" || j.type === "upload") {
                await refreshDatasets();
                const dsId = j.result?.dataset_id;
                if (typeof dsId === "string") setSelectedDatasetId(dsId);
              } else if (j.type === "train" || j.type === "retrain") {
                await refreshModels();
              } else if (j.type === "detect") {
                await refreshRuns();
                const rid = j.result?.run_id;
                if (typeof rid === "string") setSelectedRunId(rid);
              } else if (j.type === "export") {
                await refreshModels();
              }
            } else if (j.status === "failed") {
              toast(`${j.title} failed: ${j.error ?? "unknown error"}`, "error");
            } else {
              toast(`${j.title} was cancelled`, "info");
            }
          }
        } catch {
          /* transient; keep polling */
        }
      }
    };
    void tick();
    const t = setInterval(tick, 1500);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, [activeIds, refreshDatasets, refreshModels, refreshRuns, toast]);

  const activeJobs = useMemo(() => Object.values(jobs).filter((j) => !isTerminal(j.status)).sort((a, b) => a.created_at.localeCompare(b.created_at)), [jobs]);
  const area: Area = page === "models" || page === "experiments" ? "analyst" : "business";

  const value = useMemo<AppState>(
    () => ({
      page,
      area,
      setPage,
      mode,
      setMode,
      drawer,
      openDrawer: setDrawer,
      config,
      datasets,
      models,
      activeModel,
      availableModels,
      runs,
      selectedDatasetId,
      setSelectedDatasetId,
      selectedRunId,
      setSelectedRunId,
      selectedAlertId,
      setSelectedAlertId,
      drill,
      openDrill,
      actTab,
      setActTab,
      refreshDatasets,
      refreshModels,
      refreshRuns,
      activateModel,
      deleteModel,
      jobs,
      activeJobs,
      watchJob,
      cancelJob,
      toast,
      toasts,
      backendOk,
    }),
    [page, area, setPage, mode, setMode, drawer, config, datasets, models, activeModel, availableModels, runs, selectedDatasetId, selectedRunId, selectedAlertId, drill, openDrill, actTab, refreshDatasets, refreshModels, refreshRuns, activateModel, deleteModel, jobs, activeJobs, watchJob, cancelJob, toast, toasts, backendOk],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside AppProvider");
  return v;
}
