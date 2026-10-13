import { useEffect, useMemo, useState, type DragEvent } from "react";
import { ConnectorsCard } from "../components/ConnectorsCard";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import { HistogramChart, MetricBarChart } from "../components/Charts";
import { DataTable } from "../components/DataTable";
import { DataInArt, EmptyState } from "../components/Illustrations";
import { JobProgress } from "../components/JobProgress";
import { Help, Spinner, StatCard } from "../components/Layout";
import { NextStep, TechnicalDetails } from "../components/TechnicalDetails";
import type { DatasetMeta, ExportStatus, PreviewResponse, PreviewTable } from "../types";
import { estimateSeconds, featureLabel, fmtBytes, fmtDate, fmtDuration, gbp, num, titleCase } from "../utils";

function sourceLabel(d: DatasetMeta): string {
  if (d.kind === "connector") return `snapshot of ${String(d.params?.connector_name ?? "a vendor")}`;
  return d.kind === "synthetic" ? "synthetic (legacy)" : "imported";
}

function ImportCard() {
  const { config, watchJob, toast, jobs, cancelJob } = useApp();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [cmap, setCmap] = useState("");
  const [over, setOver] = useState(false);
  const [pct, setPct] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = jobId ? jobs[jobId] ?? null : null;
  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  };
  const go = async () => {
    if (!file) return;
    if (cmap.trim()) {
      try {
        JSON.parse(cmap);
      } catch {
        toast("The column map must be JSON, e.g. {\"counted_closing\": \"soh_count\"}", "error");
        return;
      }
    }
    setPct(0);
    try {
      const j = await api.datasets.upload(file, { name: name || undefined, column_map: cmap.trim() || undefined }, setPct);
      watchJob(j);
      setJobId(j.job_id);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setPct(null);
    }
  };
  return (
    <div className="card">
      <div className="card-title">
        <h2>Manual import</h2>
      </div>
      <p className="muted small">
        No connector yet? One CSV with a row per store, SKU and day (date, store, SKU, counted stock, and expected stock or opening + received + sold), or a ZIP exported from this app. Extra columns such as deliveries, returns, voids or after-hours scans make detection sharper.
      </p>
      <div className="stack" style={{ gap: 10 }}>
        <label className={`dropzone ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
          <input type="file" accept=".csv,.zip,text/csv,application/zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {file ? (
            <span>
              <b>{file.name}</b> · {fmtBytes(file.size)}
            </span>
          ) : (
            <span>Drop a CSV or ZIP here, or click to choose (up to {num.format(config.max_upload_mb)} MB)</span>
          )}
        </label>
        <label className="field">
          Name (optional)
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. North region counts, Q3" />
        </label>
        <TechnicalDetails title="Column names that differ from ours">
          <p className="small muted">
            Common names are recognised automatically (store, site, sku, article, book_qty, soh_counted, receipts, voids...). If yours differ, map them as JSON: our field to your column.
          </p>
          <textarea rows={3} value={cmap} onChange={(e) => setCmap(e.target.value)} placeholder='{"counted_closing": "physical_count", "store_id": "branch_code"}' style={{ width: "100%", fontFamily: "var(--mono)", fontSize: 12 }} />
        </TechnicalDetails>
        {pct !== null ? (
          <div>
            <div className="progress">
              <div style={{ width: `${pct * 100}%` }} />
            </div>
            <div className="small muted" style={{ marginTop: 4 }}>
              Uploading {Math.round(pct * 100)}%
            </div>
          </div>
        ) : null}
        <div className="row">
          <button className="btn primary" disabled={!file || pct !== null} onClick={go}>
            Import
          </button>
        </div>
        {job ? <JobProgress job={job} onCancel={cancelJob} /> : null}
      </div>
    </div>
  );
}

const TABLES: { key: PreviewTable; label: string }[] = [
  { key: "daily", label: "Daily records" },
  { key: "stores", label: "Stores" },
  { key: "skus", label: "SKUs" },
  { key: "lp_flags", label: "Loss-prevention flags" },
];

function DatasetDetail({ ds }: { ds: DatasetMeta }) {
  const { toast, watchJob, jobs, setPage, refreshDatasets } = useApp();
  const [table, setTable] = useState<PreviewTable>("daily");
  const [answerKey, setAnswerKey] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [exp, setExp] = useState<ExportStatus | null>(null);
  const [expJob, setExpJob] = useState<string | null>(null);
  useEffect(() => {
    setPreview(null);
    const t = answerKey && table === "daily" ? "daily" : table;
    api.datasets.preview(ds.id, t, 40, 0, answerKey).then(setPreview).catch((e) => toast(errorMessage(e), "error"));
  }, [ds.id, table, answerKey, toast]);
  const ej = expJob ? jobs[expJob] : null;
  useEffect(() => {
    api.datasets.exportStatus(ds.id).then(setExp).catch(() => setExp(null));
  }, [ds.id, ej?.status]);
  const st = ds.stats;
  const cats = useMemo(() => Object.entries(st?.rows_by_category ?? {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: titleCase(k), value: v })), [st]);
  const remove = async () => {
    if (!confirm(`Delete “${ds.name}” with its detection runs and triage history?`)) return;
    try {
      await api.datasets.delete(ds.id);
      await refreshDatasets();
      toast("Dataset deleted");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  return (
    <div className="stack">
      <div className="grid grid-4">
        <StatCard label="Store-SKU-days" value={num.format(ds.n_rows)} sub={`${ds.n_stores} stores x ${num.format(ds.n_skus)} SKUs x ${ds.n_days} days`} />
        <StatCard label="Dates" value={`${ds.n_days} days`} sub={`${ds.date_start} to ${ds.date_end}; exam from ${ds.test_from_date}`} />
        <StatCard label="Net stock gap" value={st ? gbp.format(st.net_variance_value_gbp) : "–"} sub={st ? `${num.format(st.net_variance_units)} units missing at cost, all days` : ""} />
        <StatCard label={ds.has_truth ? "Known problems (demo)" : "Loss-prevention flags"} value={ds.has_truth ? num.format(ds.n_incidents) : num.format(ds.n_lp_flags)} sub={ds.has_truth ? `incidents in the demo vendor's answer key · ${num.format(ds.n_lp_flags)} flagged by loss prevention` : "past incidents recorded"} />
      </div>
      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">
            <h3>How big are the daily stock gaps?</h3>
            <Help text="Shrinkage % = (expected - counted) / expected, for days with any gap. Most gaps are count noise of a unit or two; the long right tail is where problems hide." />
          </div>
          <HistogramChart bins={st?.shrinkage_histogram ?? []} label="Days" unit="%" />
        </div>
        <div className="card">
          <div className="card-title">
            <h3>Rows by category</h3>
          </div>
          <MetricBarChart rows={cats} metric="Store-SKU-days" format={(v) => num.format(v)} height={230} />
        </div>
      </div>
      <div className="card">
        <div className="card-title">
          <h3>Look at the data</h3>
          <div className="row" style={{ gap: 8 }}>
            {ds.has_truth && table === "daily" ? (
              <label className="check small">
                <input type="checkbox" checked={answerKey} onChange={(e) => setAnswerKey(e.target.checked)} /> show the demo answer key
              </label>
            ) : null}
            {table !== "daily" ? (
              <a className="btn sm" href={api.datasets.downloadUrl(ds.id, table as "stores" | "skus" | "lp_flags")}>
                Download CSV
              </a>
            ) : null}
          </div>
        </div>
        <div className="tabs" role="tablist">
          {TABLES.map((t) => (
            <button key={t.key} role="tab" aria-selected={table === t.key} className={table === t.key ? "active" : ""} onClick={() => setTable(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
        {preview ? (
          <>
            <DataTable columns={preview.columns} rows={preview.rows} plainHeaders stickyFirst maxHeight={360} highlight={["truth_type"]} />
            <div className="small muted" style={{ marginTop: 6 }}>
              Showing {preview.rows.length} of {num.format(preview.total_rows)} rows.
              {answerKey ? " Only a simulated vendor has an answer key. It is never shown to the models; it is only used to mark their homework." : ""}
            </div>
          </>
        ) : (
          <Spinner />
        )}
      </div>
      <div className="card">
        <div className="card-title">
          <h3>Take it with you</h3>
        </div>
        <p className="small muted">A ZIP with daily.csv, stores.csv, skus.csv, lp_flags.csv{ds.has_truth ? ", answer_key.csv" : ""} and metadata.json. Import it here again later, or open it in any tool.</p>
        <div className="row">
          <button
            className="btn"
            disabled={!!ej && !["done", "failed", "cancelled"].includes(ej.status)}
            onClick={async () => {
              try {
                const j = await api.datasets.export(ds.id);
                watchJob(j);
                setExpJob(j.job_id);
              } catch (e) {
                toast(errorMessage(e), "error");
              }
            }}
          >
            {exp?.ready ? "Rebuild ZIP" : "Build ZIP"} ({fmtDuration(estimateSeconds("export", { rows: ds.n_rows }, undefined))})
          </button>
          {exp?.ready ? (
            <a className="btn primary" href={api.datasets.exportUrl(ds.id)}>
              Download ZIP · {fmtBytes(exp.size_bytes)}
            </a>
          ) : null}
          <span className="spacer" />
          <button className="btn danger sm" onClick={remove}>
            Delete dataset
          </button>
        </div>
        {ej && ej.status !== "done" ? <JobProgress job={ej} compact /> : null}
      </div>
      <TechnicalDetails title="Technical details: columns, features and import">
        <div className="table-wrap" style={{ maxHeight: 320 }}>
          <table className="data">
            <thead>
              <tr>
                <th>Column</th>
                <th>Meaning</th>
                <th>Role</th>
                <th className="num">Mean</th>
                <th className="num">95th pct</th>
                <th className="num">Max</th>
              </tr>
            </thead>
            <tbody>
              {ds.columns.map((c) => {
                const s = st?.numeric[c.name];
                return (
                  <tr key={c.name}>
                    <td className="mono">{c.name}</td>
                    <td>{c.label ?? featureLabel(c.name)}</td>
                    <td>{c.role === "ground_truth" ? "demo answer key (never a model input)" : c.role === "feature" ? "detection feature" : c.role}</td>
                    <td className="num">{s ? s.mean.toFixed(2) : ""}</td>
                    <td className="num">{s ? num.format(s.p95) : ""}</td>
                    <td className="num">{s ? num.format(s.max) : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {ds.detection ? (
          <div className="small mt">
            <b>Column mapping:</b> {Object.entries(ds.detection.column_map).map(([k, v]) => `${k} ← ${v}`).join(", ")}
            {ds.detection.missing_optional.length ? <div className="muted">Not in the file: {ds.detection.missing_optional.join(", ")}</div> : null}
            {ds.detection.dropped_features.length ? <div className="muted">Features switched off: {ds.detection.dropped_features.map(featureLabel).join(", ")}</div> : null}
          </div>
        ) : null}
        {ds.warnings.map((w) => (
          <div key={w} className="alert warn small mt">
            {w}
          </div>
        ))}
        <div className="small muted mt">
          Id {ds.id} · created {fmtDate(ds.created_at)} · {fmtBytes(ds.size_bytes)} on disk · {num.format(ds.n_series)} store-SKU series
        </div>
      </TechnicalDetails>
      {ds.kind === "connector" ? (
        <div className="small muted">
          Snapshot of {String(ds.params?.connector_name ?? "the vendor")} ({String(ds.params?.window_start ?? ds.date_start)} to {String(ds.params?.synced_through ?? ds.date_end)}), synced {fmtDate(String(ds.params?.synced_at ?? ds.created_at))}. Each sync makes a new snapshot; team feedback carries over between them.
        </div>
      ) : null}
      <NextStep title="Next: train the detectors" description="Four methods learn what normal looks like from this vendor's own history and are marked on the last four weeks." cta="Go to Train →" onClick={() => setPage("train")} />
    </div>
  );
}

export function DataPage() {
  const { datasets, selectedDatasetId, setSelectedDatasetId } = useApp();
  const ds = datasets.find((d) => d.id === selectedDatasetId) ?? datasets[0] ?? null;
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>1 · Data</h1>
          <p>Daily stock records for every SKU in every store, read from your inventory system: what the books expect, what was counted, what moved, and how the tills behaved.</p>
        </div>
      </div>
      <div className="grid grid-side">
        <div className="stack">
          <ConnectorsCard />
          <ImportCard />
          {datasets.length ? (
            <div className="card">
              <div className="card-title">
                <h3>Your datasets</h3>
              </div>
              <div className="list">
                {datasets.map((d) => (
                  <div key={d.id} className={`list-item ${ds?.id === d.id ? "selected" : ""}`} onClick={() => setSelectedDatasetId(d.id)}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="title">{d.name}</div>
                      <div className="meta">
                        {num.format(d.n_rows)} rows · {sourceLabel(d)} · {fmtDate(d.created_at)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <div>
          {ds ? (
            <DatasetDetail key={ds.id} ds={ds} />
          ) : (
            <div className="card">
              <EmptyState art={<DataInArt />}>
                <b>No data yet.</b>
                <div className="muted">Connect your inventory system (or the bundled demo vendor) and press Sync now, or import a CSV of daily counts.</div>
              </EmptyState>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
