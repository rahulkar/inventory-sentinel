import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp } from "../context";
import type { Job } from "../types";
import { isTerminal } from "../utils";

interface Options {
  onDone?: (job: Job) => void;
  onFail?: (job: Job) => void;
  intervalMs?: number;
}

/**
 * Track one background job: polls until it reaches a terminal state and fires callbacks once.
 * The app-level watcher (context) also follows it so the header pill and list refreshes work
 * even if the page that started it unmounts.
 */
export function useJob(initial: Job | null, opts: Options = {}): { job: Job | null; running: boolean; setJob: (j: Job | null) => void } {
  const { jobs, watchJob } = useApp();
  const [job, setJobState] = useState<Job | null>(initial);
  const fired = useRef<string | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const setJob = (j: Job | null) => {
    setJobState(j);
    if (j) watchJob(j);
  };

  // Prefer the app-level copy when it is fresher.
  const shared = job ? jobs[job.job_id] : undefined;
  const current = shared && job && shared.percent >= job.percent ? shared : job;

  useEffect(() => {
    if (!job || isTerminal(job.status)) return;
    let stopped = false;
    const interval = opts.intervalMs ?? 1000;
    const t = setInterval(async () => {
      try {
        const j = await api.jobs.get(job.job_id);
        if (stopped) return;
        setJobState(j);
        if (isTerminal(j.status)) clearInterval(t);
      } catch {
        /* keep polling */
      }
    }, interval);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, [job?.job_id, job?.status, opts.intervalMs]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!current || !isTerminal(current.status) || fired.current === current.job_id) return;
    fired.current = current.job_id;
    if (current.status === "done") optsRef.current.onDone?.(current);
    else optsRef.current.onFail?.(current);
  }, [current]);

  return { job: current, running: !!current && !isTerminal(current.status), setJob };
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => (typeof window !== "undefined" ? window.matchMedia(query).matches : false));
  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = () => setMatches(mql.matches);
    handler();
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);
  return matches;
}
