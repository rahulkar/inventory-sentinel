import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { Job } from "../types";
import { isTerminal } from "../utils";

/** One button for the executive demo: create data -> train the four methods -> find anomalies.
 *  Each step is an ordinary server job (so the jobs pill, toasts and list refreshes all work); this hook only chains them
 *  and remembers where it is in localStorage so a page refresh picks the chain up again. */

export type PipelineSize = "1m" | "5m";
export type PipelineStage = "idle" | "generate" | "train" | "detect" | "done" | "failed";

export const PIPELINE_SIZES: Record<PipelineSize, { label: string; stores: number; skus: number; days: number; minutes: string }> = {
  "1m": { label: "1 million rows", stores: 40, skus: 250, days: 100, minutes: "about 1 minute" },
  "5m": { label: "5 million rows", stores: 80, skus: 500, days: 125, minutes: "about 4 minutes" },
};

export const PIPELINE_STEPS: { key: Exclude<PipelineStage, "idle" | "done" | "failed">; label: string; help: string }[] = [
  { key: "generate", label: "Create data", help: "Simulate stores, items and days with hidden problems" },
  { key: "train", label: "Train 4 methods", help: "A rule of thumb and three machine-learning methods compete" },
  { key: "detect", label: "Find anomalies", help: "Score every store-item-day with the winner" },
];

interface Saved {
  stage: PipelineStage;
  jobId: string | null;
  datasetId: string | null;
  size: PipelineSize;
  failedAt?: PipelineStage | null;
  error?: string | null;
}

const KEY = "sentinel.pipeline";
const IDLE: Saved = { stage: "idle", jobId: null, datasetId: null, size: "1m" };

function load(): Saved {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? { ...IDLE, ...(JSON.parse(raw) as Saved) } : IDLE;
  } catch {
    return IDLE;
  }
}

function save(s: Saved) {
  try {
    if (s.stage === "idle" || s.stage === "done") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable: the chain still runs, it just cannot resume after a refresh */
  }
}

export function usePipeline() {
  const { jobs, watchJob, availableModels, config } = useApp();
  const [state, setStateRaw] = useState<Saved>(load);
  const busy = useRef(false);
  const setState = useCallback((s: Saved) => {
    save(s);
    setStateRaw(s);
  }, []);

  const fail = useCallback((at: PipelineStage, e: unknown, cur: Saved) => setState({ ...cur, stage: "failed", failedAt: at, error: errorMessage(e), jobId: null }), [setState]);

  const startTrain = useCallback(
    async (cur: Saved, datasetId: string) => {
      const keys = availableModels.filter((m) => m.available && m.family !== "supervised").map((m) => m.key);
      const job = await api.train.start({
        dataset_id: datasetId,
        models: keys.map((k) => ({ key: k, params: {} })),
        run_name: "Executive demo",
        train_sample_size: config.default_train_sample,
        alert_rate: config.default_alert_rate,
        exclude_lp_flagged: true,
        random_state: 42,
      });
      watchJob(job);
      setState({ ...cur, stage: "train", jobId: job.job_id, datasetId });
    },
    [availableModels, config.default_train_sample, config.default_alert_rate, watchJob, setState],
  );

  const startDetect = useCallback(
    async (cur: Saved, datasetId: string) => {
      const job = await api.runs.detect(datasetId, null);
      watchJob(job);
      setState({ ...cur, stage: "detect", jobId: job.job_id, datasetId });
    },
    [watchJob, setState],
  );

  const start = useCallback(
    async (size: PipelineSize) => {
      const s = PIPELINE_SIZES[size];
      const base: Saved = { stage: "generate", jobId: null, datasetId: null, size };
      try {
        const job = await api.datasets.generate({ n_stores: s.stores, n_skus: s.skus, n_days: s.days, seed: 42, anomaly_multiplier: 1, lp_coverage: 0.4, name: null });
        watchJob(job);
        setState({ ...base, jobId: job.job_id });
      } catch (e) {
        fail("generate", e, base);
      }
    },
    [watchJob, setState, fail],
  );

  /** Retry the step that failed (data already created is reused). */
  const retry = useCallback(async () => {
    const cur = state;
    try {
      if (cur.failedAt === "train" && cur.datasetId) await startTrain(cur, cur.datasetId);
      else if (cur.failedAt === "detect" && cur.datasetId) await startDetect(cur, cur.datasetId);
      else await start(cur.size);
    } catch (e) {
      fail(cur.failedAt ?? "generate", e, cur);
    }
  }, [state, startTrain, startDetect, start, fail]);

  const reset = useCallback(() => setState(IDLE), [setState]);

  // After a page refresh the finished job is no longer in the app's job list: fetch it once and watch it.
  useEffect(() => {
    if (!state.jobId || jobs[state.jobId]) return;
    api.jobs
      .get(state.jobId)
      .then(watchJob)
      .catch((e) => fail(state.stage, `The server no longer knows this step (${errorMessage(e)}). It may have restarted; run the pipeline again.`, state));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.jobId]);

  // Advance when the current step's job finishes.
  const job: Job | null = state.jobId ? jobs[state.jobId] ?? null : null;
  useEffect(() => {
    if (!job || !isTerminal(job.status) || busy.current) return;
    const cur = state;
    if (job.status !== "done") {
      fail(cur.stage, job.error ?? `${job.title} was ${job.status}`, cur);
      return;
    }
    busy.current = true;
    let known = cur.datasetId;
    (async () => {
      try {
        if (cur.stage === "generate") {
          const ds = job.result?.dataset_id;
          if (typeof ds !== "string") throw new Error("The data step finished without a dataset id.");
          known = ds;
          await startTrain(cur, ds);
        } else if (cur.stage === "train" && cur.datasetId) {
          await startDetect(cur, cur.datasetId);
        } else if (cur.stage === "detect") {
          setState({ ...cur, stage: "done", jobId: null });
        }
      } catch (e) {
        fail(cur.stage === "generate" ? "train" : cur.stage === "train" ? "detect" : cur.stage, e, { ...cur, datasetId: known });
      } finally {
        busy.current = false;
      }
    })();
  }, [job?.status, job?.job_id, state, startTrain, startDetect, setState, fail]);

  const running = state.stage === "generate" || state.stage === "train" || state.stage === "detect";
  return { ...state, job, running, start, retry, reset };
}
