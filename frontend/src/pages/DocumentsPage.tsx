import { useCallback, useEffect, useState, type DragEvent, type FormEvent } from "react";
import { BookOpen, ClipboardCheck, Download, FileText, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { api } from "../api";
import { errorMessage, useApp } from "../context";
import { Spinner } from "../components/Layout";
import type { DocSearchHit, DocumentLibrary, LibraryDocument } from "../types";
import { fmtBytes, fmtDate, num } from "../utils";

type Kind = "auto" | "sop" | "reference";
const KIND_HELP: Record<Kind, string> = {
  auto: "Markdown with SOP front matter becomes a live SOP; everything else is a reference document.",
  sop: "Must be Markdown with SOP front matter (id, title, applies_to, steps). It drives the alert checklists.",
  reference: "Policies, procedures, contracts, SOP PDFs: the assistant can search and quote them.",
};
const MATCH_LABEL: Record<DocSearchHit["match"], string> = { keyword: "keywords", meaning: "meaning", both: "keywords + meaning" };

/** Documents the assistant can read: upload SOPs and reference files, see how they are indexed, test what it finds. */
export function DocumentsPage() {
  const { toast, setPage } = useApp();
  const [lib, setLib] = useState<DocumentLibrary | null>(null);
  const [kind, setKind] = useState<Kind>("auto");
  const [files, setFiles] = useState<File[]>([]);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState<{ name: string; pct: number } | null>(null);

  const load = useCallback(() => {
    api.documents.list().then(setLib).catch((e) => toast(errorMessage(e), "error"));
  }, [toast]);
  useEffect(load, [load]);
  // while passages are being embedded, refresh the progress
  useEffect(() => {
    if (!lib?.index.running) return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [lib?.index.running, load]);

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setOver(false);
    setFiles(Array.from(e.dataTransfer.files ?? []));
  };
  const upload = async () => {
    let added = 0;
    for (const f of files) {
      setBusy({ name: f.name, pct: 0 });
      try {
        const d = await api.documents.upload(f, kind, (pct) => setBusy({ name: f.name, pct }));
        if (d.duplicate) toast(`${f.name} is already in the library as ${d.name}.`, "info");
        else {
          added++;
          if (d.note) toast(`${d.name}: ${d.note}`, "info");
        }
      } catch (e) {
        toast(errorMessage(e), "error");
      }
    }
    setBusy(null);
    setFiles([]);
    if (added) toast(`${added} document${added === 1 ? "" : "s"} added. The assistant can use ${added === 1 ? "it" : "them"} now.`, "success");
    load();
  };
  const remove = async (d: LibraryDocument) => {
    if (!confirm(d.kind === "sop" ? `Delete the SOP ${d.sop_id}? Alerts will use the built-in SOP (if any) again.` : `Delete ${d.name}?`)) return;
    try {
      await api.documents.delete(d.id);
      load();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  const ix = lib?.index;
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Documents</h1>
          <p>SOPs and reference documents the assistant reads and quotes: policies, procedures, contracts, escalation guides. Uploaded SOPs also drive the checklists on alerts.</p>
        </div>
      </div>

      <div className="grid grid-side">
        <div className="stack">
          <div className="card">
            <div className="card-title">
              <h2>Add documents</h2>
            </div>
            <div className="stack" style={{ gap: 12 }}>
              <label className={`dropzone ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
                <input type="file" multiple accept={lib?.limits.types.join(",") ?? ".pdf,.docx,.md,.txt"} onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
                <Upload size={20} aria-hidden="true" />
                {files.length ? (
                  <span>
                    <b>{files.length === 1 ? files[0].name : `${files.length} files`}</b> · {fmtBytes(files.reduce((s, f) => s + f.size, 0))}
                  </span>
                ) : (
                  <span>Drop PDF, Word, Markdown or text files, or click to choose (up to {lib?.limits.max_mb ?? 25} MB each)</span>
                )}
              </label>
              <div className="seg" role="radiogroup" aria-label="Document type">
                {(["auto", "reference", "sop"] as Kind[]).map((k) => (
                  <button key={k} role="radio" aria-checked={kind === k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>
                    {k === "auto" ? "Detect" : k === "sop" ? "SOP" : "Reference"}
                  </button>
                ))}
              </div>
              <p className="small muted" style={{ margin: 0 }}>{KIND_HELP[kind]}</p>
              <button className="btn primary" disabled={!files.length || !!busy} onClick={() => void upload()}>
                {busy ? <Spinner /> : <Upload size={16} aria-hidden="true" />}
                {busy ? `Indexing ${busy.name}${busy.pct < 1 ? ` · ${Math.round(busy.pct * 100)}%` : ""}` : `Add ${files.length > 1 ? `${files.length} documents` : "document"}`}
              </button>
            </div>
          </div>

          <div className="card">
            <div className="card-title">
              <h2>How the assistant searches</h2>
              {ix ? <span className={`chip ${ix.mode === "hybrid" ? "status-done" : ""}`}>{ix.mode === "hybrid" ? "Keywords + meaning" : "Keywords only"}</span> : null}
            </div>
            {!ix ? (
              <Spinner />
            ) : (
              <div className="stack" style={{ gap: 10 }}>
                <p className="small muted" style={{ margin: 0 }}>
                  Every document is split into passages by heading. Keyword search (BM25) always works and is exact on SOP ids, store numbers and codes.
                  {ix.embedding_model ? ` Passages are also embedded with ${ix.embedding_model} through your AI gateway, so questions phrased differently still find the right passage.` : " Choose an embedding model in Settings to also match by meaning."}
                </p>
                <dl className="kv">
                  <dt>Passages</dt>
                  <dd>{num.format(ix.passages)}</dd>
                  <dt>Embedded</dt>
                  <dd>{ix.embedding_model ? `${num.format(ix.embedded)} of ${num.format(ix.passages)}` : "off"}</dd>
                </dl>
                {ix.running ? (
                  <div className="small">
                    <Spinner /> Embedding {num.format(ix.done)} of {num.format(ix.total)} new passages…
                  </div>
                ) : null}
                {ix.error ? <div className="alert warn small">{ix.error} Search falls back to keywords until it works.</div> : null}
                <div className="row">
                  {ix.embedding_model ? (
                    <button className="btn sm" disabled={ix.running || ix.embedded >= ix.passages} onClick={() => void api.documents.reindex().then(load).catch((e) => toast(errorMessage(e), "error"))}>
                      <RefreshCw size={14} aria-hidden="true" /> Embed missing passages
                    </button>
                  ) : null}
                  <button className="btn sm link" onClick={() => setPage("settings")}>
                    {ix.embedding_model ? "Change the embedding model" : "Set an embedding model"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-title">
              <h2>Library</h2>
              <span className="small muted">{lib ? `${lib.documents.length} uploaded` : ""}</span>
            </div>
            {!lib ? (
              <Spinner />
            ) : (
              <>
                {lib.documents.length ? (
                  <div className="table-wrap">
                    <table className="data">
                      <thead>
                        <tr>
                          <th>Document</th>
                          <th>Type</th>
                          <th className="num">Size</th>
                          <th className="num">Passages</th>
                          <th>Added</th>
                          <th aria-label="Actions" />
                        </tr>
                      </thead>
                      <tbody>
                        {lib.documents.map((d) => (
                          <tr key={d.id}>
                            <td className="doc-cell">
                              <div className="doc-name">
                                {d.kind === "sop" ? <ClipboardCheck size={16} aria-hidden="true" /> : <FileText size={16} aria-hidden="true" />}
                                <span>
                                  <b>{d.name}</b>
                                  {d.kind === "sop" ? <span className="small muted"> · SOP {d.sop_id}{d.note ? ` · ${d.note}` : ""}</span> : null}
                                </span>
                              </div>
                            </td>
                            <td>
                              <span className={`chip ${d.kind === "sop" ? "status-done" : "status-queued"}`}>{d.kind === "sop" ? "SOP" : "Reference"}</span>
                            </td>
                            <td className="num">{fmtBytes(d.size_bytes)}</td>
                            <td className="num">{d.kind === "sop" ? `${d.n_chunks} steps` : num.format(d.n_chunks)}</td>
                            <td>{fmtDate(d.created_at)}</td>
                            <td>
                              <div className="row" style={{ gap: 2, flexWrap: "nowrap" }}>
                                <a className="icon-btn ghost" href={api.documents.fileUrl(d.id)} title="Download the original" aria-label={`Download ${d.name}`}>
                                  <Download size={15} aria-hidden="true" />
                                </a>
                                <button className="icon-btn ghost danger" onClick={() => void remove(d)} title="Delete" aria-label={`Delete ${d.name}`}>
                                  <Trash2 size={15} aria-hidden="true" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted small">Nothing uploaded yet. The assistant already reads the sources below.</p>
                )}
                <div className="builtin-docs">
                  <span className="small muted">Always available:</span>
                  {lib.builtin.map((b) => (
                    <span key={b.name} className="chip" title={`${b.n_chunks} passages`}>
                      <BookOpen size={12} aria-hidden="true" /> {b.name}
                    </span>
                  ))}
                </div>
              </>
            )}
          </div>

          <SearchTester />
        </div>
      </div>
    </div>
  );
}

/** Ask a question and see the passages the assistant's search_docs tool would receive. */
function SearchTester() {
  const { toast } = useApp();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<DocSearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (e: FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    try {
      setHits((await api.documents.search(q.trim(), 5)).hits);
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card">
      <div className="card-title">
        <h2>Test what the assistant finds</h2>
      </div>
      <form className="search-row" onSubmit={(e) => void run(e)}>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. who approves a refund without a receipt?" aria-label="Question" />
        <button className="btn" type="submit" disabled={busy || !q.trim()}>
          {busy ? <Spinner /> : <Search size={16} aria-hidden="true" />} Search
        </button>
      </form>
      {hits === null ? null : hits.length === 0 ? (
        <p className="muted small mt">No passage matches. Try other words, or upload the document that answers it.</p>
      ) : (
        <ol className="doc-hits">
          {hits.map((h, i) => (
            <li key={i}>
              <div className="doc-hit-head">
                <b>{h.source}</b>
                <span className="small muted">{h.section !== h.source ? h.section : ""}</span>
                <span className={`chip match-${h.match}`}>{MATCH_LABEL[h.match]}</span>
              </div>
              <p className="small">{h.text}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
