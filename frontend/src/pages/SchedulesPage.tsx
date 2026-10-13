import { ArrowRight, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import { HyperparamForm } from "../components/HyperparamForm";
import { EmptyState, RoadmapArt } from "../components/Illustrations";
import { JobProgress } from "../components/JobProgress";
import { Help, Spinner } from "../components/Layout";
import { ProposalCard } from "../components/ProposalCard";
import { TechnicalDetails } from "../components/TechnicalDetails";
import type { Proposal, Schedule, ScheduleIn, SchedulerStatus, ScheduleRun, Severity } from "../types";
import { fmtDate, gbp, num } from "../utils";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const ZONES = ["Europe/London", "Europe/Dublin", "Europe/Paris", "UTC", "America/New_York", "America/Chicago", "America/Los_Angeles", "Asia/Kolkata", "Asia/Singapore", "Australia/Sydney"];
const SEVERITIES: Severity[] = ["critical", "high", "medium"];

function localZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/London";
  } catch {
    return "Europe/London";
  }
}

function blank(connectorId: string): ScheduleIn {
  return {
    name: "Nightly scan",
    enabled: true,
    connector_id: connectorId,
    timezone: localZone(),
    frequency: { kind: "daily", every_hours: 6, at: "06:00", days: [0, 1, 2, 3, 4, 5, 6] },
    pipeline: {
      sync: true,
      model_policy: "active",
      model_id: null,
      train: { models: [{ key: "iforest", params: {} }], train_sample_size: 100_000, alert_rate: 0.008, activate_retrained: false, min_interval_days: 0 },
      auto_tasks: { enabled: false, severities: ["critical"], min_value_gbp: 0, max_tasks: 10 },
    },
    catch_up: "once",
  };
}

function toIn(s: Schedule): ScheduleIn {
  const { name, enabled, connector_id, timezone, frequency, pipeline, catch_up } = s;
  return { name, enabled, connector_id, timezone, frequency, pipeline, catch_up };
}

function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "–";
}

function RunStatus({ r }: { r: Partial<ScheduleRun> }) {
  const st = r.status ?? "queued";
  const cls = st === "skipped" ? "neutral" : `status-${st}`;
  return <span className={`chip ${cls}`}>{st === "done" ? "done" : st}</span>;
}

// ---------------------------------------------------------------- editor
function Editor({ initial, scheduleId, onSaved, onCancel }: { initial: ScheduleIn; scheduleId: string | null; onSaved: (s: Schedule) => void; onCancel: () => void }) {
  const { connectors, models, availableModels, toast } = useApp();
  const [f, setF] = useState<ScheduleIn>(initial);
  const [preview, setPreview] = useState<{ summary: string; next_runs: string[] } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const p = f.pipeline;
  const set = (patch: Partial<ScheduleIn>) => setF((cur) => ({ ...cur, ...patch }));
  const setFreq = (patch: Partial<ScheduleIn["frequency"]>) => setF((cur) => ({ ...cur, frequency: { ...cur.frequency, ...patch } }));
  const setPipe = (patch: Partial<ScheduleIn["pipeline"]>) => setF((cur) => ({ ...cur, pipeline: { ...cur.pipeline, ...patch } }));
  const setTrain = (patch: Partial<ScheduleIn["pipeline"]["train"]>) => setPipe({ train: { ...p.train, ...patch } });
  const setAuto = (patch: Partial<ScheduleIn["pipeline"]["auto_tasks"]>) => setPipe({ auto_tasks: { ...p.auto_tasks, ...patch } });
  const algos = availableModels.filter((m) => m.available && m.family !== "supervised");
  const saved = models.filter((m) => m.key !== "reranker" || m.parent_model_id).sort((a, b) => (b.metrics.average_precision ?? -1) - (a.metrics.average_precision ?? -1));

  useEffect(() => {
    const t = setTimeout(() => {
      api.schedules
        .preview(f)
        .then((r) => {
          setPreview(r);
          setProblem(null);
        })
        .catch((e) => {
          setPreview(null);
          setProblem(errorMessage(e));
        });
    }, 350);
    return () => clearTimeout(t);
  }, [f]);

  const toggleAlgo = (key: string) => {
    const on = p.train.models.some((m) => m.key === key);
    const next = on ? p.train.models.filter((m) => m.key !== key) : [...p.train.models, { key, params: {} }];
    setTrain({ models: next });
  };

  const save = async () => {
    setBusy(true);
    try {
      const s = scheduleId ? await api.schedules.update(scheduleId, f) : await api.schedules.create(f);
      toast(scheduleId ? "Schedule saved" : `Scheduled: next run ${when(s.next_run_at)}`, "success");
      onSaved(s);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="card-title">
        <h2>{scheduleId ? "Edit schedule" : "New schedule"}</h2>
      </div>
      <div className="stack" style={{ gap: 14 }}>
        <div className="form-grid">
          <label className="field">
            Name
            <input type="text" value={f.name} onChange={(e) => set({ name: e.target.value })} />
          </label>
          <label className="field">
            Vendor connector
            <select value={f.connector_id} onChange={(e) => set({ connector_id: e.target.value })}>
              {connectors.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div>
          <div className="small muted" style={{ marginBottom: 6 }}>
            When
          </div>
          <div className="row" style={{ gap: 6 }}>
            {(["daily", "weekly", "interval"] as const).map((k) => (
              <button key={k} className={`toggle-chip ${f.frequency.kind === k ? "on" : ""}`} aria-pressed={f.frequency.kind === k} onClick={() => setFreq({ kind: k, days: k === "daily" ? [0, 1, 2, 3, 4, 5, 6] : f.frequency.days })}>
                {k === "daily" ? "Every day" : k === "weekly" ? "Some weekdays" : "Every few hours"}
              </button>
            ))}
          </div>
          <div className="form-grid mt">
            {f.frequency.kind === "interval" ? (
              <label className="field">
                Every (hours)
                <input type="number" min={1} max={168} value={f.frequency.every_hours} onChange={(e) => setFreq({ every_hours: Number(e.target.value) })} />
              </label>
            ) : (
              <label className="field">
                At
                <input type="time" value={f.frequency.at} onChange={(e) => setFreq({ at: e.target.value || "06:00" })} />
              </label>
            )}
            <label className="field">
              Time zone
              <input type="text" list="tz-list" value={f.timezone} onChange={(e) => set({ timezone: e.target.value })} />
              <datalist id="tz-list">
                {ZONES.map((z) => (
                  <option key={z} value={z} />
                ))}
              </datalist>
            </label>
          </div>
          {f.frequency.kind !== "daily" ? (
            <div className="row mt" style={{ gap: 6 }}>
              {DAYS.map((d, i) => {
                const on = f.frequency.days.includes(i);
                return (
                  <button key={d} className={`toggle-chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => setFreq({ days: on ? f.frequency.days.filter((x) => x !== i) : [...f.frequency.days, i].sort() })}>
                    {d}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>

        <div>
          <div className="small muted" style={{ marginBottom: 6 }}>
            Which model scores the new data <Help text="Detectors learn what is normal for this vendor. Retraining each run follows drift (new lines, seasons) but takes longer; a fixed model gives stable, comparable scores." />
          </div>
          <div className="grid grid-3">
            {(
              [
                ["active", "The model in use", "Whatever model is in use when the run starts (switch it on the Models page)."],
                ["fixed", "A specific saved model", "Always the same model, so scores stay comparable run to run."],
                ["retrain", "Retrain each run", "Train the algorithms you pick on the fresh snapshot, then score with the best."],
              ] as const
            ).map(([k, label, help]) => (
              <button key={k} className={`radio-card ${p.model_policy === k ? "on" : ""}`} aria-pressed={p.model_policy === k} onClick={() => setPipe({ model_policy: k })} style={{ textAlign: "left" }}>
                <b>{label}</b>
                <div className="small muted">{help}</div>
              </button>
            ))}
          </div>
          {p.model_policy === "fixed" ? (
            <label className="field mt">
              Model
              <select value={p.model_id ?? ""} onChange={(e) => setPipe({ model_id: e.target.value || null })}>
                <option value="">Choose a model…</option>
                {saved.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.label} · {m.dataset_name.slice(0, 40)} · AP {m.metrics.average_precision?.toFixed(2) ?? "–"}
                    {m.is_active ? " (in use)" : ""}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {p.model_policy === "retrain" ? (
            <div className="stack mt" style={{ gap: 8 }}>
              <div className="row" style={{ gap: 6 }}>
                {algos.map((a) => {
                  const on = p.train.models.some((m) => m.key === a.key);
                  return (
                    <button key={a.key} className={`toggle-chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => toggleAlgo(a.key)} title={a.description}>
                      {a.label}
                    </button>
                  );
                })}
              </div>
              <div className="form-grid">
                <label className="field">
                  Training sample (rows)
                  <select value={p.train.train_sample_size} onChange={(e) => setTrain({ train_sample_size: Number(e.target.value) })}>
                    {[30_000, 60_000, 100_000, 200_000, 500_000].map((n) => (
                      <option key={n} value={n}>
                        {num.format(n)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>
                    Retrain at most every (days) <Help text="0 = retrain on every run. Otherwise reuse this schedule's last model until it is this old." />
                  </span>
                  <input type="number" min={0} max={90} value={p.train.min_interval_days} onChange={(e) => setTrain({ min_interval_days: Number(e.target.value) })} />
                </label>
              </div>
              <label className="check small">
                <input type="checkbox" checked={p.train.activate_retrained} onChange={(e) => setTrain({ activate_retrained: e.target.checked })} /> Make the retrained model the one in use
              </label>
              <TechnicalDetails title="Algorithm settings">
                {p.train.models.map((sel) => {
                  const spec = algos.find((a) => a.key === sel.key);
                  return spec ? (
                    <div key={sel.key} className="mt">
                      <b className="small">{spec.label}</b>
                      <HyperparamForm params={spec.params} values={sel.params} onChange={(name, value) => setTrain({ models: p.train.models.map((m) => (m.key === sel.key ? { ...m, params: { ...m.params, [name]: value } } : m)) })} />
                    </div>
                  ) : null;
                })}
              </TechnicalDetails>
            </div>
          ) : null}
        </div>

        <div>
          <label className="check">
            <input type="checkbox" checked={p.auto_tasks.enabled} onChange={(e) => setAuto({ enabled: e.target.checked })} /> Propose vendor tasks for new alerts
            <Help text="Uses the SOP for each alert's type (recount, receiving check, till audit…). Tasks are only proposed: someone approves them on this page within 72 hours." />
          </label>
          {p.auto_tasks.enabled ? (
            <div className="form-grid mt">
              <div className="field">
                Severities
                <div className="row" style={{ gap: 6 }}>
                  {SEVERITIES.map((sv) => {
                    const on = p.auto_tasks.severities.includes(sv);
                    return (
                      <button key={sv} className={`toggle-chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => setAuto({ severities: on ? p.auto_tasks.severities.filter((x) => x !== sv) : [...p.auto_tasks.severities, sv] })}>
                        {sv}
                      </button>
                    );
                  })}
                </div>
              </div>
              <label className="field">
                Min. value at risk (£)
                <input type="number" min={0} value={p.auto_tasks.min_value_gbp} onChange={(e) => setAuto({ min_value_gbp: Number(e.target.value) })} />
              </label>
              <label className="field">
                Max tasks per run
                <input type="number" min={1} max={50} value={p.auto_tasks.max_tasks} onChange={(e) => setAuto({ max_tasks: Number(e.target.value) })} />
              </label>
            </div>
          ) : null}
        </div>

        <TechnicalDetails title="More options">
          <label className="check small">
            <input type="checkbox" checked={p.sync} onChange={(e) => setPipe({ sync: e.target.checked })} /> Sync the vendor first (off: score the latest snapshot)
          </label>
          <label className="field mt" style={{ maxWidth: 360 }}>
            If Sentinel was off at the scheduled time
            <select value={f.catch_up} onChange={(e) => set({ catch_up: e.target.value as "once" | "skip" })}>
              <option value="once">Run once when it is back (catch up)</option>
              <option value="skip">Skip the missed run</option>
            </select>
          </label>
        </TechnicalDetails>

        {problem ? <div className="alert warn small">{problem}</div> : null}
        {preview ? (
          <div className="alert info small">
            {preview.summary}. Next: {preview.next_runs.map(when).join(" · ")}.
          </div>
        ) : null}
        <div className="row">
          <button className="btn primary" disabled={busy || !!problem || !f.name} onClick={save}>
            {busy ? <Spinner /> : null} {scheduleId ? "Save schedule" : "Create schedule"}
          </button>
          <button className="btn link" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- history
function History({ schedule }: { schedule: Schedule }) {
  const { setSelectedRunId, setPage, setActTab, refreshRuns, jobs, cancelJob, models } = useApp();
  const [runs, setRuns] = useState<ScheduleRun[] | null>(null);
  const load = useCallback(() => api.schedules.runs(schedule.id, 30).then(setRuns).catch(() => setRuns([])), [schedule.id]);
  const lastJobStatus = schedule.last_run?.job_id ? jobs[schedule.last_run.job_id]?.status : undefined;
  useEffect(() => {
    void load();
  }, [load, schedule.last_run?.status, lastJobStatus]);
  const live = runs?.find((r) => (r.status === "queued" || r.status === "running") && r.job_id && jobs[r.job_id]);
  const modelName = (id: string | null) => models.find((m) => m.model_id === id)?.label ?? id ?? "–";
  const open = async (r: ScheduleRun) => {
    if (!r.detection_run_id) return;
    await refreshRuns();
    setSelectedRunId(r.detection_run_id);
    setActTab("alerts");
    setPage("act");
  };
  return (
    <div className="card">
      <div className="card-title">
        <h3>Run history · {schedule.name}</h3>
        <button className="btn sm link" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {live && live.job_id ? <JobProgress job={jobs[live.job_id]} compact onCancel={cancelJob} /> : null}
      {runs === null ? (
        <Spinner />
      ) : runs.length === 0 ? (
        <div className="muted small">No runs yet. Press “Run now” to try it.</div>
      ) : (
        <div className="table-wrap" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead>
              <tr>
                <th>Started</th>
                <th>How</th>
                <th>Status</th>
                <th>Data through</th>
                <th>Model</th>
                <th className="num">New alerts</th>
                <th className="num">Critical</th>
                <th className="num">£ at risk</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} title={r.error ?? r.warnings.join(" ") ?? ""}>
                  <td>{fmtDate(r.started_at)}</td>
                  <td>{r.trigger === "catch_up" ? "catch-up" : r.trigger === "manual" ? "run now" : "timer"}</td>
                  <td>
                    <RunStatus r={r} />
                    {r.retrained ? <span className="chip neutral" style={{ marginLeft: 4 }}>retrained</span> : null}
                  </td>
                  <td>{r.data_through ?? "–"}</td>
                  <td className="small">{r.model_id ? modelName(r.model_id) : "–"}</td>
                  <td className="num">{r.new_alerts ?? "–"}</td>
                  <td className="num">{r.new_critical ?? "–"}</td>
                  <td className="num">{r.value_at_risk_gbp !== null ? gbp.format(r.value_at_risk_gbp) : "–"}</td>
                  <td>
                    {r.detection_run_id ? (
                      <button className="btn sm link" onClick={() => void open(r)}>
                        Alerts <ArrowRight size={16} aria-hidden="true" />
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {runs?.filter((r) => r.status === "failed" || r.warnings.length).slice(0, 3).map((r) => (
        <div key={r.run_id} className={`alert ${r.status === "failed" ? "error" : "warn"} small mt`}>
          <b>{fmtDate(r.started_at)}:</b> {r.error ?? r.warnings[0]}
          {r.sop_id && !(r.error ?? "").includes(r.sop_id) ? <> Follow SOP <span className="mono">{r.sop_id}</span>{r.error_kind ? ` (error kind: ${r.error_kind})` : ""}.</> : null}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- page
export function SchedulesPage() {
  const { connectors, toast, watchJob, setPage, selectedScheduleId, setSelectedScheduleId, refreshDatasets, refreshRuns, jobs } = useApp();
  const [items, setItems] = useState<Schedule[] | null>(null);
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [pending, setPending] = useState<Proposal[]>([]);
  const [editing, setEditing] = useState<{ id: string | null; body: ScheduleIn } | null>(null);
  const load = useCallback(async () => {
    try {
      const [s, st, p] = await Promise.all([api.schedules.list(), api.schedules.status(), api.schedules.pendingApprovals()]);
      setItems(s);
      setStatus(st);
      setPending(p);
    } catch (e) {
      toast(errorMessage(e), "error");
      setItems([]);
    }
  }, [toast]);
  useEffect(() => {
    void load();
    const t = setInterval(load, 15_000);
    return () => clearInterval(t);
  }, [load]);
  // reload as soon as a scheduled pipeline finishes (its new alerts may have proposed vendor tasks)
  const pipelineKey = useMemo(
    () =>
      Object.values(jobs)
        .filter((j) => j.type === "pipeline")
        .map((j) => `${j.job_id}:${j.status}`)
        .sort()
        .join(","),
    [jobs],
  );
  useEffect(() => {
    if (pipelineKey) void load();
  }, [pipelineKey, load]);
  const selected = useMemo(() => items?.find((s) => s.id === selectedScheduleId) ?? items?.[0] ?? null, [items, selectedScheduleId]);

  const runNow = async (s: Schedule) => {
    try {
      const out = await api.schedules.run(s.id);
      if (out.job) {
        watchJob(out.job);
        toast(`Started: ${s.name}`, "success");
      } else toast(out.run.error ?? "Skipped", "info");
      setSelectedScheduleId(s.id);
      await load();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  const toggle = async (s: Schedule) => {
    try {
      await api.schedules.setEnabled(s.id, !s.enabled);
      await load();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  const remove = async (s: Schedule) => {
    if (!confirm(`Delete the schedule “${s.name}”? Its run history stays in the log.`)) return;
    try {
      await api.schedules.delete(s.id);
      await load();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  const approve = async (id: string) => {
    try {
      const out = await api.assistant.confirm(id);
      if (out.proposal.status === "failed") toast(out.proposal.error ?? "Could not raise the tasks", "error");
      else toast(`Done: ${out.proposal.title}`, "success");
      await Promise.all([load(), refreshDatasets(), refreshRuns()]);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  const decline = async (id: string) => {
    await api.assistant.cancel(id).catch((e) => toast(errorMessage(e), "error"));
    await load();
  };

  if (!connectors.length) {
    return (
      <div className="stack">
        <div className="page-header">
          <div>
            <h1>Schedules</h1>
            <p>Run sync → model → detection automatically at set times.</p>
          </div>
        </div>
        <div className="card">
          <EmptyState art={<RoadmapArt />}>
            <b>Connect a data source first.</b>
            <div className="muted">Schedules pull fresh data from a vendor connector before each run.</div>
            <button className="btn primary mt" onClick={() => setPage("data")}>
              Go to Data <ArrowRight size={16} aria-hidden="true" />
            </button>
          </EmptyState>
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Schedules</h1>
          <p>At the times you choose, Sentinel syncs the vendor, scores the new days with the model you pick (or retrains one), and proposes vendor tasks from the SOPs for a person to approve.</p>
        </div>
        <div className="row">
          {status ? <span className={`chip ${status.running ? "status-done" : "status-failed"}`} title={status.last_tick ? `Last check ${fmtDate(status.last_tick)}` : undefined}>{status.running ? `Scheduler on · checks every ${status.tick_seconds}s` : "Scheduler off"}</span> : null}
          <button className="btn primary" onClick={() => setEditing({ id: null, body: blank(connectors[0].id) })}>
            <Plus size={16} aria-hidden="true" /> New schedule
          </button>
        </div>
      </div>

      {pending.length ? (
        <div className="card accent">
          <div className="card-title">
            <h3>Waiting for your approval</h3>
            <span className="chip primary">{pending.length}</span>
          </div>
          <p className="small muted">Vendor tasks proposed by scheduled runs. Nothing is sent to the vendor until someone approves; proposals expire after 72 hours.</p>
          <div className="stack" style={{ gap: 8 }}>
            {pending.map((p) => (
              <ProposalCard key={p.proposal_id} p={p} onConfirm={approve} onCancel={decline} />
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid grid-side">
        <div className="stack">
          {items === null ? <Spinner /> : null}
          {items?.length === 0 && !editing ? (
            <div className="card">
              <EmptyState art={<RoadmapArt />}>
                <b>No schedules yet.</b>
                <div className="muted">A nightly scan after the vendor closes the day is a good start.</div>
              </EmptyState>
            </div>
          ) : null}
          {items?.map((s) => {
            const lr = s.last_run;
            return (
              <div key={s.id} className={`card subtle list-item ${selected?.id === s.id ? "selected" : ""}`} onClick={() => setSelectedScheduleId(s.id)} style={{ display: "block", cursor: "pointer" }}>
                <div className="row between">
                  <b>{s.name}</b>
                  <label className="check small" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={s.enabled} onChange={() => void toggle(s)} /> {s.enabled ? "on" : "paused"}
                  </label>
                </div>
                <div className="small muted" style={{ margin: "4px 0" }}>
                  {s.enabled ? <>Next run {when(s.next_run_at)}</> : "Paused"} · {s.pipeline.model_policy === "retrain" ? `retrains ${s.pipeline.train.models.map((m) => m.key).join(" + ")}` : s.pipeline.model_policy === "fixed" ? "fixed model" : "model in use"}
                  {s.pipeline.auto_tasks.enabled ? " · proposes tasks" : ""}
                </div>
                {lr ? (
                  <div className="small">
                    Last: <RunStatus r={lr} /> {lr.finished_at ? fmtDate(lr.finished_at) : lr.started_at ? fmtDate(lr.started_at) : ""}
                    {lr.new_alerts !== null && lr.new_alerts !== undefined ? ` · ${lr.new_alerts} new alerts` : ""}
                  </div>
                ) : null}
                <div className="row mt" onClick={(e) => e.stopPropagation()}>
                  <button className="btn sm primary" onClick={() => void runNow(s)}>
                    Run now
                  </button>
                  <button className="btn sm" onClick={() => setEditing({ id: s.id, body: toIn(s) })}>
                    Edit
                  </button>
                  <span className="spacer" />
                  <button className="btn sm link" onClick={() => void remove(s)}>
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <div className="stack">
          {editing ? (
            <Editor
              key={editing.id ?? "new"}
              initial={editing.body}
              scheduleId={editing.id}
              onSaved={async (s) => {
                setEditing(null);
                setSelectedScheduleId(s.id);
                await load();
              }}
              onCancel={() => setEditing(null)}
            />
          ) : selected ? (
            <History schedule={selected} />
          ) : null}
          {!editing && selected ? <StatusLine s={selected} /> : null}
        </div>
      </div>
    </div>
  );
}

function StatusLine({ s }: { s: Schedule }) {
  return (
    <div className="small muted">
      {s.name}: {s.frequency.kind === "interval" ? `every ${s.frequency.every_hours} h` : `${s.frequency.kind === "daily" ? "every day" : s.frequency.days.map((d) => DAYS[d]).join(", ")} at ${s.frequency.at}`} ({s.timezone}) · catch-up {s.catch_up === "once" ? "on" : "off"}
      {s.last_retrain_at ? ` · last retrained ${fmtDate(s.last_retrain_at)}` : ""}.
    </div>
  );
}
