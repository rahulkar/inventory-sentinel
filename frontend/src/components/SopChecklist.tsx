import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { AlertSop, SopStep, StockPosition, VendorTask } from "../types";
import { num } from "../utils";
import { Spinner } from "./Layout";
import { TechnicalDetails } from "./TechnicalDetails";

const PRIORITIES = ["low", "normal", "high", "urgent"];

function doneKey(alertKey: string, stepId: string): string {
  return `sentinel.sop.${alertKey}.${stepId}`;
}

function readDone(alertKey: string, stepId: string): boolean {
  try {
    return window.localStorage.getItem(doneKey(alertKey, stepId)) === "1";
  } catch {
    return false;
  }
}

function TaskChip({ t }: { t: VendorTask }) {
  const cls = t.status === "done" ? "status-done" : t.status === "rejected" ? "status-failed" : "status-running";
  return (
    <span className={`chip ${cls}`} title={`${t.title}${t.outcome ? ` · outcome: ${t.outcome}` : ""}`}>
      {t.task_id} · {t.status}
      {t.outcome ? ` · ${t.outcome.replace(/_/g, " ")}` : ""}
    </span>
  );
}

/** Confirm panel for raising one vendor task: the click on "Send to vendor" is the person's approval. */
function VendorTaskDialog({ sop, step, runId, onDone, onCancel }: { sop: AlertSop; step: SopStep; runId: string; onDone: () => void; onCancel: () => void }) {
  const { toast } = useApp();
  const vt = step.vendor_task!;
  const [priority, setPriority] = useState(vt.priority ?? (sop.alert.severity === "critical" ? "urgent" : sop.alert.severity === "high" ? "high" : "normal"));
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const vendorName = "the vendor's back-office";
  const send = async () => {
    setBusy(true);
    try {
      const res = await api.vendorTasks.raise([{ run_id: runId, alert_id: sop.alert.alert_id, type: vt.type, priority, sop_id: sop.sop.id, sop_step: step.id, note: note || null }], sop.connector_id);
      if (res.created.length) toast(`Raised ${res.created[0].task_id} in ${vendorName}`, "success");
      else if (res.existing.length) toast(`Already raised: ${res.existing[0].task_id}`, "info");
      else toast(res.failed[0]?.error ?? "Could not raise the task", "error");
      onDone();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card subtle mt" role="dialog" aria-label="Raise vendor task">
      <div className="small">
        Send a <b>{vt.type.replace(/_/g, " ")}</b> task to {vendorName}: <i>{vt.title}</i>
      </div>
      <div className="form-grid mt">
        <label className="field">
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            {PRIORITIES.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Note for the store (optional)
          <input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. check the returns cage too" />
        </label>
      </div>
      <div className="small muted mt">Store staff see it in their back-office; Sentinel reads the outcome back on the next sync and records it as team feedback.</div>
      <div className="row mt">
        <button className="btn primary sm" disabled={busy} onClick={send}>
          {busy ? <Spinner /> : null} Send to vendor
        </button>
        <button className="btn sm link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function LiveStock({ connectorId, storeId, skuId }: { connectorId: string; storeId: string; skuId: string }) {
  const [pos, setPos] = useState<StockPosition | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const look = async () => {
    setBusy(true);
    setErr(null);
    try {
      setPos(await api.connectors.lookup(connectorId, storeId, skuId, 7));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt">
      <button className="btn sm" onClick={look} disabled={busy}>
        {busy ? <Spinner /> : null} Check live stock in the vendor system
      </button>
      {err ? <div className="alert error small mt">{err}</div> : null}
      {pos ? (
        <div className="small mt">
          <b>{pos.on_hand ?? "–"}</b> on hand as of {pos.as_of} (live).
          <div className="table-wrap mt" style={{ maxHeight: 200 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Day</th>
                  <th className="num">Received</th>
                  <th className="num">Sold</th>
                  <th className="num">Expected</th>
                  <th className="num">Counted</th>
                  <th className="num">Gap</th>
                </tr>
              </thead>
              <tbody>
                {pos.last_days.map((d) => (
                  <tr key={d.date}>
                    <td>{d.date}</td>
                    <td className="num">{num.format(d.received)}</td>
                    <td className="num">{num.format(d.sold)}</td>
                    <td className="num">{num.format(d.expected_closing)}</td>
                    <td className="num">{num.format(d.counted_closing)}</td>
                    <td className="num">{num.format(d.variance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** The SOP for one alert: escalation level, a checklist of steps, and approved write-back to the vendor. */
export function SopChecklist({ runId, alertId, compact = false }: { runId: string; alertId: string; compact?: boolean }) {
  const [sop, setSop] = useState<AlertSop | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [raising, setRaising] = useState<string | null>(null);
  const [, setTick] = useState(0);
  const load = useCallback(() => {
    api.sops
      .forAlert(runId, alertId)
      .then((x) => {
        setSop(x);
        setErr(null);
      })
      .catch((e) => setErr(errorMessage(e)));
  }, [runId, alertId]);
  useEffect(() => {
    setSop(null);
    load();
  }, [load]);
  if (err) return <div className="small muted">No SOP available: {err}</div>;
  if (!sop) return <Spinner />;
  const esc = sop.escalation;
  const toggle = (stepId: string) => {
    try {
      const k = doneKey(sop.alert.alert_key, stepId);
      if (window.localStorage.getItem(k) === "1") window.localStorage.removeItem(k);
      else window.localStorage.setItem(k, "1");
    } catch {
      /* storage unavailable: the tick is not remembered */
    }
    setTick((t) => t + 1);
  };
  const canRaise = (s: SopStep) => !!s.vendor_task && sop.can_raise_tasks && (!sop.task_types.length || sop.task_types.includes(s.vendor_task.type));
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="row between">
        <div>
          <b>{sop.sop.title}</b> <span className="small muted">SOP {sop.sop.id} · v{sop.sop.version}{sop.sop.owner_role ? ` · owner: ${sop.sop.owner_role}` : ""}</span>
        </div>
        {esc ? (
          <span className={`chip ${esc.level === "L3" ? "sev-critical" : esc.level === "L2" ? "sev-high" : "sev-medium"}`} title={esc.notify.length ? `Tell: ${esc.notify.join(", ")}` : undefined}>
            {esc.label}
            {esc.response_hours ? ` · within ${esc.response_hours} h` : ""}
          </span>
        ) : null}
      </div>
      {esc?.notify.length && !compact ? <div className="small muted">Tell: {esc.notify.join(", ")}.</div> : null}
      <ol className="story-list numbered" style={{ margin: 0 }}>
        {sop.steps.map((s) => {
          const done = readDone(sop.alert.alert_key, s.id);
          return (
            <li key={s.id} style={{ marginBottom: 8 }}>
              <label className="check" style={{ alignItems: "flex-start" }}>
                {compact ? null : <input type="checkbox" checked={done} onChange={() => toggle(s.id)} aria-label={`Mark step ${s.id} done`} />}
                <span style={{ textDecoration: done ? "line-through" : undefined }}>
                  {s.text}
                  <span className="small muted">
                    {" "}
                    {s.role ? `· ${s.role}` : ""}
                    {s.due_hours ? ` · within ${s.due_hours} h` : ""}
                  </span>
                </span>
              </label>
              {s.evidence.length && !compact ? <div className="small muted" style={{ marginLeft: 23 }}>Evidence: {s.evidence.join("; ")}</div> : null}
              <div className="row" style={{ gap: 6, marginLeft: compact ? 0 : 23, marginTop: 4 }}>
                {s.raised.map((t) => (
                  <TaskChip key={t.task_id} t={t} />
                ))}
                {canRaise(s) && !s.raised.length && raising !== s.id ? (
                  <button className="btn sm" onClick={() => setRaising(s.id)}>
                    Raise {s.vendor_task!.type.replace(/_/g, " ")} task →
                  </button>
                ) : null}
              </div>
              {raising === s.id ? (
                <VendorTaskDialog
                  sop={sop}
                  step={s}
                  runId={runId}
                  onDone={() => {
                    setRaising(null);
                    load();
                  }}
                  onCancel={() => setRaising(null)}
                />
              ) : null}
            </li>
          );
        })}
      </ol>
      {!sop.can_raise_tasks && sop.steps.some((s) => s.vendor_task) ? (
        <div className="small muted">Vendor tasks need a vendor connector: this run is on {sop.connector_id ? "a connector that does not accept tasks" : "imported data"}.</div>
      ) : null}
      {sop.connector_id && !compact ? <LiveStock connectorId={sop.connector_id} storeId={sop.alert.store_id} skuId={sop.alert.sku_id} /> : null}
      {!compact ? (
        <TechnicalDetails title="Closure and how outcomes map to feedback">
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {sop.sop.closure.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          {Object.keys(sop.sop.triage_mapping).length ? (
            <div className="small mt">
              {Object.entries(sop.sop.triage_mapping)
                .map(([k, v]) => `${k} → ${v.replace(/_/g, " ")}`)
                .join(" · ")}
            </div>
          ) : null}
        </TechnicalDetails>
      ) : null}
    </div>
  );
}
