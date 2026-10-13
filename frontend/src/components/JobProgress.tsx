import type { ReactNode } from "react";
import { Check, Circle, LoaderCircle, Minus, X } from "lucide-react";
import type { Job } from "../types";
import { fmtClock, fmtDuration, isTerminal } from "../utils";

const ICON: Record<string, ReactNode> = {
  queued: <Circle size={13} />,
  running: <LoaderCircle size={13} className="spin" />,
  done: <Check size={14} strokeWidth={3} />,
  failed: <X size={14} strokeWidth={3} />,
  cancelled: <Minus size={14} />,
};

export function JobProgress({ job, onCancel, compact = false }: { job: Job | null; onCancel?: (id: string) => void; compact?: boolean }) {
  if (!job) return null;
  const active = !isTerminal(job.status);
  const pct = job.status === "done" ? 100 : Math.max(0, Math.min(100, job.percent));
  return (
    <div className={`job ${compact ? "compact" : ""} status-${job.status}`}>
      <div className="row between" style={{ marginBottom: 6 }}>
        <div>
          <b>{job.title}</b>
          {job.queue_position ? <span className="small muted"> · waiting, {job.queue_position} ahead</span> : null}
        </div>
        <div className="row" style={{ gap: 8 }}>
          <span className={`chip status-${job.status}`}>{job.status}</span>
          {active && onCancel ? (
            <button className="btn sm" onClick={() => onCancel(job.job_id)}>
              Cancel
            </button>
          ) : null}
        </div>
      </div>
      <div className="progress">
        <div style={{ width: `${pct}%` }} />
      </div>
      <div className="row between small muted" style={{ marginTop: 6 }}>
        <span>
          {job.step ?? (job.status === "queued" ? "Waiting for the previous job" : job.status === "done" ? "Finished" : job.status)}
          {job.message ? ` · ${job.message}` : ""}
        </span>
        <span>
          {pct.toFixed(0)}% · {fmtClock(job.elapsed_seconds)}
          {active && job.eta_seconds !== null ? ` · ${fmtDuration(job.eta_seconds)} left` : ""}
        </span>
      </div>
      {!compact && job.steps.length ? (
        <ul className="progress-steps">
          {job.steps.map((s) => (
            <li key={s.key} className={`step-${s.status}`}>
              <span className="ico" aria-hidden="true">
                {ICON[s.status] ?? ICON.queued}
              </span>
              {s.label}
              {s.seconds !== null && s.status === "done" ? <span className="muted"> · {fmtClock(s.seconds)}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {job.warnings.map((w, i) => (
        <div key={i} className="alert warn" style={{ marginTop: 8 }}>
          {w}
        </div>
      ))}
      {job.error && job.status !== "cancelled" ? (
        <div className="alert error" style={{ marginTop: 8 }}>
          {job.error}
        </div>
      ) : null}
    </div>
  );
}
