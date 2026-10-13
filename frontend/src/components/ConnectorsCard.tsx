import { useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import type { Connector, ConnectorIn, ConnectorTest } from "../types";
import { fmtDate, fmtDuration, num } from "../utils";
import { JobProgress } from "./JobProgress";
import { Help, Spinner } from "./Layout";
import { TechnicalDetails } from "./TechnicalDetails";

const EMPTY: ConnectorIn = { name: "", url: "", token: "", window_days: 120, resync_days: 3, retention: 3, use_answer_key: true, feedback_from_tasks: true, enabled: true };

function SyncState({ c }: { c: Connector }) {
  const s = c.last_sync;
  if (!s) return <span className="chip neutral">never synced</span>;
  if (s.status === "running") return <span className="chip status-running">syncing…</span>;
  if (s.status === "failed") return <span className="chip status-failed">last sync failed</span>;
  return <span className="chip status-done">synced through {s.synced_through}</span>;
}

function ConnectorForm({ initial, connectorId, onDone, onCancel }: { initial: ConnectorIn; connectorId?: string; onDone: (c: Connector) => void; onCancel: () => void }) {
  const { toast } = useApp();
  const [f, setF] = useState<ConnectorIn>(initial);
  const [test, setTest] = useState<ConnectorTest | null>(null);
  const [busy, setBusy] = useState<"test" | "save" | null>(null);
  const set = (patch: Partial<ConnectorIn>) => {
    setF((cur) => ({ ...cur, ...patch }));
    setTest(null);
  };
  const runTest = async () => {
    setBusy("test");
    try {
      setTest(await api.connectors.testDraft(f, connectorId));
    } catch (e) {
      setTest({ ok: false, capabilities: null, error: errorMessage(e), seconds: 0 });
    } finally {
      setBusy(null);
    }
  };
  const save = async () => {
    setBusy("save");
    try {
      const c = connectorId ? await api.connectors.update(connectorId, f) : await api.connectors.create(f);
      toast(connectorId ? "Connector saved" : `Connected to ${c.capabilities?.vendor?.name ?? c.name}`, "success");
      onDone(c);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };
  const caps = test?.capabilities;
  return (
    <div className="stack" style={{ gap: 10 }}>
      <label className="field">
        Name
        <input type="text" value={f.name} onChange={(e) => set({ name: e.target.value })} placeholder="e.g. Head-office stock system" />
      </label>
      <label className="field">
        <span>
          MCP endpoint URL <Help text="The vendor's MCP server (streamable HTTP) implementing the Sentinel Inventory Connector contract, e.g. http://127.0.0.1:8020/mcp/ for the demo vendor." />
        </span>
        <input type="url" value={f.url} onChange={(e) => set({ url: e.target.value })} placeholder="https://vendor.example.com/mcp/" />
      </label>
      <label className="field">
        Access token (optional)
        <input type="password" autoComplete="off" value={f.token ?? ""} onChange={(e) => set({ token: e.target.value })} placeholder={connectorId ? "leave as is to keep the saved token" : "sent as Authorization: Bearer …"} />
      </label>
      <TechnicalDetails title="Sync settings">
        <div className="form-grid">
          <label className="field">
            <span>
              Days per snapshot <Help text="Each sync builds a snapshot of the vendor's last N days. Models train on its history and are tested on its last 28%." />
            </span>
            <input type="number" min={28} max={730} value={f.window_days} onChange={(e) => set({ window_days: Number(e.target.value) })} />
          </label>
          <label className="field">
            <span>
              Re-read recent days <Help text="Each sync pulls only new days plus this many recent days, to pick up late corrections." />
            </span>
            <input type="number" min={0} max={30} value={f.resync_days} onChange={(e) => set({ resync_days: Number(e.target.value) })} />
          </label>
          <label className="field">
            Snapshots to keep
            <input type="number" min={1} max={20} value={f.retention} onChange={(e) => set({ retention: Number(e.target.value) })} />
          </label>
          <label className="field">
            Header
            <input type="text" value={f.auth_header ?? "Authorization"} onChange={(e) => set({ auth_header: e.target.value })} />
          </label>
        </div>
        <label className="check small">
          <input type="checkbox" checked={f.feedback_from_tasks} onChange={(e) => set({ feedback_from_tasks: e.target.checked })} /> Use closed vendor tasks as team feedback
        </label>
        <label className="check small">
          <input type="checkbox" checked={f.use_answer_key} onChange={(e) => set({ use_answer_key: e.target.checked })} /> Use a demo vendor's answer key to score models (only simulated vendors have one)
        </label>
      </TechnicalDetails>
      {test ? (
        test.ok && caps ? (
          <div className="alert info small">
            <b>{caps.vendor?.name}</b> answered in {test.seconds.toFixed(1)} s · contract {caps.contract} v{caps.version}
            {caps.status === "ready" ? (
              <>
                {" "}
                · {num.format(caps.counts?.stores ?? 0)} stores, {num.format(caps.counts?.skus ?? 0)} products, data {caps.data_range?.first_date} to {caps.data_range?.last_date}
              </>
            ) : (
              <> · still loading ({caps.status})</>
            )}
            {caps.features?.answer_key ? " · demo answer key available" : ""}
          </div>
        ) : (
          <div className="alert error small">{test.error}</div>
        )
      ) : null}
      <div className="row">
        <button className="btn" disabled={!f.url || busy !== null} onClick={runTest}>
          {busy === "test" ? <Spinner /> : null} Test connection
        </button>
        <button className="btn primary" disabled={!f.url || !f.name || busy !== null} onClick={save}>
          {busy === "save" ? <Spinner /> : null} {connectorId ? "Save" : "Add connector"}
        </button>
        <button className="btn link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function ConnectorRow({ c }: { c: Connector }) {
  const { watchJob, jobs, toast, cancelJob, refreshConnectors } = useApp();
  const [editing, setEditing] = useState(false);
  const [jobId, setJobId] = useState<string | null>(c.last_sync?.status === "running" ? c.last_sync.job_id : null);
  const job = jobId ? jobs[jobId] ?? null : null;
  const running = !!job && !["done", "failed", "cancelled"].includes(job.status);
  const caps = c.capabilities;
  const sync = async (full = false) => {
    try {
      const j = await api.connectors.sync(c.id, full);
      watchJob(j);
      setJobId(j.job_id);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  const remove = async () => {
    if (!confirm(`Remove the connector “${c.name}”? Its snapshots stay until you delete them.`)) return;
    try {
      await api.connectors.delete(c.id);
      await refreshConnectors();
      toast("Connector removed");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  if (editing) {
    return (
      <div className="card subtle">
        <ConnectorForm
          initial={{ name: c.name, url: c.url, token: c.token, auth_header: c.auth_header, auth_scheme: c.auth_scheme, window_days: c.window_days, resync_days: c.resync_days, retention: c.retention, use_answer_key: c.use_answer_key, feedback_from_tasks: c.feedback_from_tasks, enabled: c.enabled }}
          connectorId={c.id}
          onDone={async () => {
            setEditing(false);
            await refreshConnectors();
          }}
          onCancel={() => setEditing(false)}
        />
      </div>
    );
  }
  const s = c.last_sync;
  return (
    <div className="card subtle">
      <div className="row between">
        <div style={{ minWidth: 0 }}>
          <div className="title">
            <b>{c.name}</b> {caps?.vendor?.name && caps.vendor.name !== c.name ? <span className="muted small">· {caps.vendor.name}</span> : null}
          </div>
          <div className="small muted mono" style={{ overflowWrap: "anywhere" }}>
            {c.url}
          </div>
        </div>
        <SyncState c={c} />
      </div>
      <div className="small muted mt">
        {s?.at ? <>Last sync {fmtDate(s.at)}{s.rows ? ` · ${num.format(s.rows)} rows in the snapshot` : ""}{s.seconds ? ` · took ${fmtDuration(s.seconds)}` : ""}. </> : null}
        {caps?.data_range?.last_date ? <>Vendor data through {caps.data_range.last_date}. </> : null}
        Keeps the last {c.window_days} days; {c.retention} snapshots.
        {caps?.features?.answer_key ? " Demo vendor: has an answer key for scoring." : ""}
      </div>
      {s?.status === "failed" && s.error ? <div className="alert error small mt">{s.error} See SOP “data-feed-failure”.</div> : null}
      {s?.warnings?.map((w) => (
        <div key={w} className="alert warn small mt">
          {w}
        </div>
      ))}
      <div className="row mt">
        <button className="btn primary sm" disabled={running || !c.enabled} onClick={() => sync(false)}>
          Sync now
        </button>
        <button className="btn sm" disabled={running} onClick={() => sync(true)} title="Re-pull the whole window">
          Full re-sync
        </button>
        {caps?.backoffice_url ? (
          <a className="btn sm" href={caps.backoffice_url} target="_blank" rel="noreferrer">
            Open back-office ↗
          </a>
        ) : null}
        <span className="spacer" />
        <button className="btn link sm" onClick={() => setEditing(true)}>
          Edit
        </button>
        <button className="btn link sm" onClick={remove}>
          Remove
        </button>
      </div>
      {job && (running || job.status === "failed") ? <div className="mt"><JobProgress job={job} onCancel={cancelJob} compact /></div> : null}
    </div>
  );
}

/** Data page: where inventory comes from. Sentinel reads each vendor's system over MCP; models learn that vendor's own normal. */
export function ConnectorsCard() {
  const { connectors, refreshConnectors } = useApp();
  const [adding, setAdding] = useState(false);
  return (
    <div className="card">
      <div className="card-title">
        <h2>Connect a data source</h2>
        {connectors.length ? <span className="chip primary">{connectors.length} connected</span> : null}
      </div>
      <p className="muted small">
        Sentinel reads daily stock movements from your inventory system over MCP, keeps a rolling snapshot, and trains on <i>that</i> system's own history, so “normal” means normal for your stores. It can send approved recount and investigation tasks back.
      </p>
      <div className="stack" style={{ gap: 10 }}>
        {connectors.map((c) => (
          <ConnectorRow key={c.id} c={c} />
        ))}
        {adding ? (
          <div className="card subtle">
            <ConnectorForm
              initial={connectors.length ? EMPTY : { ...EMPTY, name: "Demo vendor (simulated)", url: "http://127.0.0.1:8020/mcp/" }}
              onDone={async () => {
                setAdding(false);
                await refreshConnectors();
              }}
              onCancel={() => setAdding(false)}
            />
          </div>
        ) : (
          <div className="row">
            <button className="btn" onClick={() => setAdding(true)}>
              + Add a connector
            </button>
            {!connectors.length ? <span className="small muted">Try the bundled demo vendor: start it with the dev scripts, then add it here.</span> : null}
          </div>
        )}
      </div>
    </div>
  );
}
