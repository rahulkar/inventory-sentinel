import { useState } from "react";
import { useApp } from "../context";
import type { Proposal } from "../types";
import { fmtDate, fmtDuration } from "../utils";
import { JobProgress } from "./JobProgress";
import { Spinner } from "./Layout";
import { TechnicalDetails } from "./TechnicalDetails";

/** A proposed action waiting for a person's OK: used in the chat and for approvals from scheduled runs. */
export function ProposalCard({ p, onConfirm, onCancel, confirmLabel }: { p: Proposal; onConfirm: (id: string) => Promise<unknown>; onCancel: (id: string) => Promise<unknown> | void; confirmLabel?: string }) {
  const { jobs } = useApp();
  const job = p.job_id ? jobs[p.job_id] : null;
  const [busy, setBusy] = useState(false);
  const isTask = p.kind === "vendor_task";
  const created = (p.result?.created as unknown[] | undefined)?.length;
  return (
    <div className={`proposal-card status-${p.status}`}>
      <div className="row between">
        <b>{p.title}</b>
        <span className={`chip ${p.status === "pending" ? "primary" : p.status === "confirmed" ? "status-done" : p.status === "failed" ? "status-failed" : "neutral"}`}>{p.status === "pending" ? "needs your OK" : p.status}</span>
      </div>
      <div className="muted small" style={{ margin: "6px 0" }}>
        {p.summary}
        {p.estimate_seconds ? ` Estimated ${fmtDuration(p.estimate_seconds)}.` : ""}
        {p.source === "scheduler" ? ` Proposed by a scheduled run on ${fmtDate(p.created_at)}.` : ""}
      </div>
      {p.warnings.map((w, i) => (
        <div key={i} className="alert warn small" style={{ marginBottom: 6 }}>
          {w}
        </div>
      ))}
      {p.error ? <div className="alert error small">{p.error}</div> : null}
      {p.status === "confirmed" && isTask && created !== undefined ? <div className="alert info small">{created} task{created === 1 ? "" : "s"} raised in the vendor's back-office.</div> : null}
      {p.status === "pending" ? (
        <div className="row">
          <button
            className="btn primary sm"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm(p.proposal_id);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? <Spinner /> : null} {confirmLabel ?? (isTask ? "Approve and raise" : "Confirm and run")}
          </button>
          <button className="btn sm" disabled={busy} onClick={() => void onCancel(p.proposal_id)}>
            Not now
          </button>
        </div>
      ) : null}
      {job ? (
        <div style={{ marginTop: 8 }}>
          <JobProgress job={job} compact />
        </div>
      ) : null}
      <TechnicalDetails title="Parameters">
        <pre className="code-block" style={{ margin: 0 }}>{JSON.stringify(p.params, null, 1)}</pre>
      </TechnicalDetails>
    </div>
  );
}
