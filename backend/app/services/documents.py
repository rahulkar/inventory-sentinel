"""Document library for the assistant: uploaded SOPs and reference documents, plus semantic search over everything it reads.

Storage is one SQLite file (config.KNOWLEDGE_DB) next to the originals in config.DOCS_DIR:
- documents: what was uploaded (name, kind, size, hash, chunk count, status)
- chunks:    heading-aware passages of each reference document (the same splitter as the built-in guide)
- embeddings: a cache of vectors keyed by (embedding model, content hash). Every passage the assistant can search,
  built-in or uploaded, is embedded once per model and reused, so changing nothing costs nothing.

Embeddings come from the same LiteLLM gateway as the chat (OpenAI-compatible /v1/embeddings), so there is no model to
host here. For a library of this size (thousands of passages) a brute-force cosine over a float32 matrix takes about a
millisecond, so no vector database is needed. When no embedding model is set, or the gateway is down, search is
keyword-only (BM25) and nothing breaks.

A Markdown upload with the SOP front matter (docs/sops/README.md) becomes a live SOP in config.USER_SOPS_DIR: the alert
drill-down uses it as a checklist and an uploaded SOP replaces a built-in one with the same id.
"""
from __future__ import annotations

import base64
import hashlib
import re
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx
import numpy as np

from app import config
from app.services import storage

_lock = threading.RLock()
_embed_state: dict[str, Any] = {"running": False, "done": 0, "total": 0, "error": None, "model": None, "finished_at": None}
_SCHEMA = """
create table if not exists documents (
  id text primary key, name text not null, kind text not null, ext text not null, size_bytes integer not null,
  sha256 text not null, n_chunks integer not null default 0, n_words integer not null default 0, sop_id text,
  created_at text not null, note text
);
create table if not exists chunks (
  doc_id text not null, ord integer not null, section text not null, text text not null, primary key (doc_id, ord)
);
create table if not exists embeddings (
  model text not null, hash text not null, dim integer not null, vec blob not null, primary key (model, hash)
);
"""


def _db() -> sqlite3.Connection:
    config.ensure_dirs()
    con = sqlite3.connect(config.KNOWLEDGE_DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def chunk_hash(section: str, text: str) -> str:
    return hashlib.sha1(f"{section}\n{text}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- text extraction
_PDF_HEADING = re.compile(r"^\d{1,2}(\.\d{1,2})*\.?\s+[A-Z][^.:;]{2,70}$")  # "5. Response levels", "2.1 Scope" (no full stop)


def extract_text(path: Path, ext: str) -> str:
    """Plain text with Markdown headings where the format has them, so passages keep their section names."""
    if ext in (".md", ".markdown", ".txt"):
        raw = path.read_bytes()
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        out = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            out.append(f"# Page {i + 1}")
            # PDF text has no heading markup: numbered section titles ("7. Police and HR referrals", "2.1 Scope")
            # become headings so passages are cut, and cited, per section
            out += [f"## {ln.strip()}" if _PDF_HEADING.match(ln.strip()) else ln for ln in text.splitlines()]
        return "\n".join(out)
    if ext == ".docx":
        return _docx_text(path)
    raise ValueError(f"Unsupported file type {ext}.")


def _docx_text(path: Path) -> str:
    """Paragraphs of a .docx (Word headings become Markdown headings, table cells become lines), stdlib only."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    lines: list[str] = []
    for p in root.iter(f"{{{ns['w']}}}p"):
        text = "".join(t.text or "" for t in p.iter(f"{{{ns['w']}}}t")).strip()
        if not text:
            continue
        style = p.find("w:pPr/w:pStyle", ns)
        name = (style.get(f"{{{ns['w']}}}val") if style is not None else "") or ""
        m = re.match(r"(?i)heading\s*(\d)", name)
        level = int(m.group(1)) if m else (1 if name.lower() == "title" else 0)
        lines.append(f"{'#' * min(level, 4)} {text}" if level else text)
    return "\n".join(lines)


# ---------------------------------------------------------------- documents
def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {k: r[k] for k in r.keys()}


def list_documents() -> list[dict[str, Any]]:
    with _lock, _db() as con:
        return [_row(r) for r in con.execute("select * from documents order by created_at desc")]


def get(doc_id: str) -> dict[str, Any]:
    with _lock, _db() as con:
        r = con.execute("select * from documents where id = ?", (doc_id,)).fetchone()
    if r is None:
        raise LookupError(f"Document {doc_id} not found")
    return _row(r)


def original_path(doc: dict[str, Any]) -> Path:
    if doc["kind"] == "sop":
        return config.USER_SOPS_DIR / f"{doc['sop_id']}.md"
    return config.DOCS_DIR / f"{doc['id']}{doc['ext']}"


def version() -> tuple[int, str]:
    """Changes whenever a document is added or removed (part of the search index's signature)."""
    with _lock, _db() as con:
        r = con.execute("select count(*) n, coalesce(max(created_at), '') m from documents").fetchone()
    return int(r["n"]), str(r["m"])


def reference_chunks() -> list[tuple[str, str, str, str]]:
    """(doc_id, document name, section, text) for every passage of every uploaded reference document."""
    with _lock, _db() as con:
        rows = con.execute("select c.doc_id, d.name, c.section, c.text from chunks c join documents d on d.id = c.doc_id order by d.created_at, c.ord").fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def add(tmp: Path, filename: str, kind: str = "auto") -> dict[str, Any]:
    """Index an uploaded file. kind: "auto" (SOP if it has SOP front matter), "sop" or "reference". Consumes `tmp`."""
    from app.assistant import knowledge
    from app.services import sops

    ext = Path(filename).suffix.lower()
    name = Path(filename).name[:200]
    if ext not in config.DOC_TYPES:
        storage.safe_unlink(tmp)
        raise ValueError(f"{name}: upload PDF, Word (.docx), Markdown or text files.")
    size = tmp.stat().st_size
    if size > config.DOC_MAX_MB * 1024 * 1024:
        storage.safe_unlink(tmp)
        raise ValueError(f"{name} is over the {config.DOC_MAX_MB} MB limit for documents.")
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    with _lock, _db() as con:
        dup = con.execute("select * from documents where sha256 = ?", (digest,)).fetchone()
    if dup is not None:
        storage.safe_unlink(tmp)
        return {**_row(dup), "duplicate": True}

    sop = None
    if ext in (".md", ".markdown") and kind in ("auto", "sop"):
        try:
            sop = sops.parse(tmp)
        except Exception as exc:  # noqa: BLE001 - a broken front matter is reported, not a 500
            if kind == "sop":
                storage.safe_unlink(tmp)
                raise ValueError(f"{name}: the SOP front matter could not be read ({exc}).") from exc
    if kind == "sop" and sop is None:
        storage.safe_unlink(tmp)
        raise ValueError(f"{name}: an SOP must be Markdown starting with YAML front matter (id, title, applies_to, steps...). See docs/sops/README.md; other files can be added as reference documents.")

    doc_id = storage.new_id("doc")
    now = storage.now_iso()
    if sop is not None:
        dest = config.USER_SOPS_DIR / f"{re.sub(r'[^A-Za-z0-9_.-]', '-', sop.id)}.md"
        replaced = dest.exists() or sop.id in sops.load()
        tmp.replace(dest)
        note = f"Replaces the built-in SOP {sop.id}." if replaced else None
        with _lock, _db() as con:
            # one record per live SOP: uploading a new version of the same id replaces the old record
            con.execute("delete from documents where kind = 'sop' and sop_id = ?", (sop.id,))
            con.execute(
                "insert into documents (id, name, kind, ext, size_bytes, sha256, n_chunks, n_words, sop_id, created_at, note) values (?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, name, "sop", ext, size, digest, len(sop.steps), len(sop.body.split()), sop.id, now, note),
            )
    else:
        try:
            text = extract_text(tmp, ext)
        except Exception as exc:  # noqa: BLE001
            storage.safe_unlink(tmp)
            raise ValueError(f"{name}: could not read the file ({exc}).") from exc
        parts = knowledge.split_sections(text, name)
        if not parts:
            storage.safe_unlink(tmp)
            raise ValueError(f"{name}: no text found. A scanned PDF needs OCR before it can be searched.")
        tmp.replace(config.DOCS_DIR / f"{doc_id}{ext}")
        with _lock, _db() as con:
            con.execute(
                "insert into documents (id, name, kind, ext, size_bytes, sha256, n_chunks, n_words, sop_id, created_at, note) values (?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, name, "reference", ext, size, digest, len(parts), sum(len(c.text.split()) for c in parts), None, now, None),
            )
            con.executemany("insert into chunks (doc_id, ord, section, text) values (?,?,?,?)", [(doc_id, i, c.section, c.text) for i, c in enumerate(parts)])
    start_embedding()
    return get(doc_id)


def delete(doc_id: str) -> bool:
    doc = get(doc_id)
    path = original_path(doc)
    with _lock, _db() as con:
        con.execute("delete from chunks where doc_id = ?", (doc_id,))
        con.execute("delete from documents where id = ?", (doc_id,))
    storage.safe_unlink(path)
    return True


def preview(doc_id: str, n: int = 3) -> list[dict[str, Any]]:
    doc = get(doc_id)
    if doc["kind"] == "sop":
        from app.services import sops

        s = sops.load().get(doc["sop_id"])
        return [{"section": s.title, "text": (s.summary or "") + "\n" + "\n".join(f"{i + 1}. {st.text}" for i, st in enumerate(s.steps))}] if s else []
    with _lock, _db() as con:
        rows = con.execute("select section, text from chunks where doc_id = ? order by ord limit ?", (doc_id, n)).fetchall()
    return [{"section": r[0], "text": r[1][:600]} for r in rows]


# ---------------------------------------------------------------- embeddings (via the LiteLLM gateway)
def embedding_model() -> str:
    from app.assistant import settings as llm

    s = llm.load()
    return s.embedding_model.strip() if s.base_url and s.embedding_model.strip() else ""


EMBED_MAX_CHARS = 8000  # ~2,000 tokens: well inside the 8,191-token input limit of OpenAI-style embedding models
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _vector(e: Any) -> np.ndarray:
    """One embedding from the response: a list of floats, or base64 float32 when a gateway encodes it that way."""
    if isinstance(e, str):
        return np.frombuffer(base64.b64decode(e), dtype=np.float32)
    return np.asarray(e, dtype=np.float32)


def _post(texts: list[str], timeout: float) -> np.ndarray:
    from app.assistant import settings as llm

    s = llm.load()
    for attempt in range(4):
        r = httpx.post(
            f"{s.base_url}/v1/embeddings", json={"model": s.embedding_model.strip(), "input": texts}, headers=llm._headers(s.api_key),
            timeout=timeout, verify=llm.verify_arg(s.verify_ssl, s.ca_bundle),
        )
        if r.status_code in _RETRY_STATUS and attempt < 3:  # rate limit or a busy upstream: back off and try again
            wait = float(r.headers.get("retry-after") or 0) or 1.5 * 2**attempt
            time.sleep(min(wait, 20.0))
            continue
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
        v = np.stack([_vector(d["embedding"]) for d in data]) if data else np.zeros((0, 1), dtype=np.float32)
        if v.shape[0] != len(texts):
            raise ValueError(f"the gateway returned {v.shape[0]} vectors for {len(texts)} passages")
        return v
    raise RuntimeError("unreachable")


def embed(texts: list[str], timeout: float) -> np.ndarray:
    """Unit-length float32 vectors for `texts` from the gateway's OpenAI-compatible /v1/embeddings endpoint.

    Inputs are trimmed to EMBED_MAX_CHARS and never empty. A batch the gateway refuses as too large (some hosted models
    take only 16 inputs per request) is split in half and retried, down to one input per request.
    """
    texts = [(t or "").strip()[:EMBED_MAX_CHARS] or "." for t in texts]
    try:
        v = _post(texts, timeout)
    except httpx.HTTPStatusError as exc:
        if len(texts) > 1 and exc.response.status_code in (400, 413, 422):
            half = len(texts) // 2
            v = np.concatenate([embed(texts[:half], timeout), embed(texts[half:], timeout)])
        else:
            raise
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def cached_vectors(model: str, hashes: list[str]) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    with _lock, _db() as con:
        for i in range(0, len(hashes), 500):
            part = hashes[i : i + 500]
            q = f"select hash, vec from embeddings where model = ? and hash in ({','.join('?' * len(part))})"
            for h, blob in con.execute(q, (model, *part)):
                out[h] = np.frombuffer(blob, dtype=np.float32)
    return out


def _store(model: str, hashes: list[str], vecs: np.ndarray) -> None:
    with _lock, _db() as con:
        con.executemany("insert or replace into embeddings (model, hash, dim, vec) values (?,?,?,?)", [(model, h, int(v.shape[0]), v.astype(np.float32).tobytes()) for h, v in zip(hashes, vecs)])


def embed_status() -> dict[str, Any]:
    return dict(_embed_state)


def start_embedding() -> bool:
    """Embed, in the background, every searchable passage that has no vector yet for the current model."""
    model = embedding_model()
    if not model:
        return False
    with _lock:
        if _embed_state["running"]:
            return False
        _embed_state.update(running=True, done=0, total=0, error=None, model=model)
    threading.Thread(target=_embed_missing, args=(model,), daemon=True, name="embed-docs").start()
    return True


def _embed_missing(model: str) -> None:
    from app.assistant import knowledge

    try:
        chunks = knowledge.index().chunks
        todo: dict[str, str] = {}
        for c in chunks:
            todo.setdefault(c.hash, f"{c.section}\n{c.text}")
        have = cached_vectors(model, list(todo))
        missing = [(h, t) for h, t in todo.items() if h not in have]
        _embed_state.update(total=len(missing))
        for i in range(0, len(missing), config.EMBED_BATCH):
            part = missing[i : i + config.EMBED_BATCH]
            vecs = embed([t for _, t in part], timeout=config.EMBED_TIMEOUT_S)
            _store(model, [h for h, _ in part], vecs)
            _embed_state.update(done=_embed_state["done"] + len(part))
    except Exception as exc:  # noqa: BLE001 - shown on the Documents page; search stays keyword-only meanwhile
        _embed_state.update(error=_readable(exc))
    finally:
        _embed_state.update(running=False, finished_at=storage.now_iso())


def _readable(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text[:200].replace("\n", " ")
        return f"The gateway refused the embedding request ({exc.response.status_code}): {body}"
    if isinstance(exc, httpx.HTTPError):
        return "Cannot reach the gateway for embeddings. Check the URL, VPN or proxy."
    return str(exc)[:300]


_qcache: dict[tuple[str, str], tuple[float, np.ndarray]] = {}


def query_vector(query: str) -> np.ndarray | None:
    """The query's vector, or None (no embedding model, or the gateway did not answer in time)."""
    model = embedding_model()
    if not model or not query.strip():
        return None
    key = (model, query.strip().lower())
    hit = _qcache.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    try:
        v = embed([query], timeout=config.EMBED_QUERY_TIMEOUT_S)[0]
    except Exception as exc:  # noqa: BLE001 - fall back to keyword search
        _embed_state.update(error=_readable(exc))
        return None
    if len(_qcache) > 500:
        _qcache.clear()
    _qcache[key] = (time.time(), v)
    return v
