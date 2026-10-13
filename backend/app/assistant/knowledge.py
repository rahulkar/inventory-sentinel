"""The assistant's knowledge library: the user guide, README, story, glossary, every SOP and the documents uploaded on the
Documents page. Keyword search (BM25) always works; when an embedding model is set in Settings, passages are also
ranked by meaning (vectors cached in services/documents.py) and the two rankings are merged (reciprocal rank fusion)."""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app import config
from app.assistant import plain_language
from app.services import documents

DOCS = [
    ("README", config.ROOT / "README.md"),
    ("GUIDE", config.ROOT / "GUIDE.md"),
    ("Story", Path(__file__).parent / "knowledge" / "story.md"),
    ("Connector contract", config.ROOT / "docs" / "connector-contract.md"),
]


def sop_markdown(sop) -> str:  # type: ignore[no-untyped-def]
    """An SOP as searchable Markdown: summary, steps (with roles and deadlines), escalation, closure and the body."""
    lines = [f"# {sop.title}", sop.summary or ""]
    if sop.steps:
        lines.append("## Steps")
        for st in sop.steps:
            due = f" within {st.due_hours:g} h" if st.due_hours else ""
            task = f" (vendor task: {st.vendor_task.get('type')})" if st.vendor_task else ""
            lines.append(f"- {st.text} [{st.role or 'owner'}{due}]{task}")
    if sop.escalation:
        lines.append("## Escalation")
        for r in sop.escalation:
            lines.append(f"- {r.get('label')}: severity {', '.join(r.get('severities') or ['any'])}, value at risk from £{r.get('min_value_gbp', 0)}, respond within {r.get('response_hours')} h, tell {', '.join(r.get('notify') or [])}")
    if sop.closure:
        lines += ["## Closure"] + [f"- {c}" for c in sop.closure]
    return "\n".join(lines) + "\n\n" + sop.body
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "it", "with", "as", "by", "at", "be", "this", "that", "are", "from", "its", "into", "than", "then", "so", "you", "your", "we", "our", "i", "my", "me", "how", "what", "does", "do", "can", "will"}
_TOKEN = re.compile(r"[a-z0-9£%]+")
TOC_HEADINGS = {"contents", "table of contents"}


@dataclass
class Chunk:
    source: str
    section: str
    text: str
    tokens: list[str]
    hash: str = ""
    doc_id: str | None = None  # set for passages of an uploaded reference document


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


def split_sections(text: str, source: str, max_words: int = 250) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading_path: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        buf.clear()
        # a table of contents lists every heading, so it would match almost any query
        if not body or (heading_path and heading_path[-1].lower() in TOC_HEADINGS):
            return
        words = body.split()
        section = " › ".join(heading_path) or source
        for i in range(0, len(words), max_words):
            part = " ".join(words[i : i + max_words])
            chunks.append(Chunk(source=source, section=section, text=part, tokens=tokenize(section + " " + part), hash=documents.chunk_hash(section, part)))

    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,4})\s+(.*)", line)  # "# comment" lines in code blocks are not headings
        if m:
            flush()
            level = len(m.group(1))
            heading_path = heading_path[: level - 1] + [m.group(2).strip()]
        else:
            buf.append(line)
    flush()
    return chunks


class BM25:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.n = len(chunks)
        self.avgdl = sum(len(c.tokens) for c in chunks) / max(self.n, 1)
        self.df: Counter[str] = Counter()
        for c in chunks:
            self.df.update(set(c.tokens))
        self.tf = [Counter(c.tokens) for c in chunks]

    def score(self, query: list[str], i: int) -> float:
        tf = self.tf[i]
        dl = len(self.chunks[i].tokens)
        s = 0.0
        for q in query:
            if q not in tf:
                continue
            idf = math.log(1 + (self.n - self.df[q] + 0.5) / (self.df[q] + 0.5))
            f = tf[q]
            s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1)))
        return s

    def rank(self, query: str, n: int) -> list[tuple[float, int]]:
        q = tokenize(query)
        if not q:
            return []
        scored = [(self.score(q, i), i) for i in range(self.n)]
        scored = [sc for sc in scored if sc[0] > 0]
        scored.sort(key=lambda x: -x[0])
        return scored[:n]

    def search(self, query: str, k: int = 4) -> list[tuple[float, Chunk]]:
        return [(s, self.chunks[i]) for s, i in self.rank(query, k)]


_index: tuple[tuple, BM25] | None = None


def _signature() -> tuple:
    from app.services import sops

    return tuple(p.stat().st_mtime if p.exists() else -1.0 for _, p in DOCS) + (sops.signature(), documents.version())


def index() -> BM25:
    global _index
    sig = _signature()
    if _index and _index[0] == sig:
        return _index[1]
    chunks: list[Chunk] = []
    for name, path in DOCS:
        if path.exists():
            chunks += split_sections(path.read_text(encoding="utf-8"), name)
    chunks += split_sections(plain_language.glossary_markdown(), "Glossary")
    from app.services import sops

    for sop in sops.load().values():
        chunks += split_sections(sop_markdown(sop), f"SOP {sop.id}")
    for doc_id, name, section, text in documents.reference_chunks():
        chunks.append(Chunk(source=name, section=section, text=text, tokens=tokenize(section + " " + text), hash=documents.chunk_hash(section, text), doc_id=doc_id))
    _index = (sig, BM25(chunks))
    return _index[1]


_matrix: tuple[tuple, np.ndarray, np.ndarray] | None = None  # (key, row -> chunk index, unit vectors)


def _vectors(bm: BM25, model: str) -> tuple[np.ndarray, np.ndarray]:
    """The cached vectors of the index's passages for `model` (passages not embedded yet are simply left out)."""
    global _matrix
    st = documents.embed_status()
    key = (id(bm), model, st.get("done"), st.get("finished_at"), int(time.time() // 30) if st.get("running") else 0)
    if _matrix and _matrix[0] == key:
        return _matrix[1], _matrix[2]
    have = documents.cached_vectors(model, [c.hash for c in bm.chunks])
    rows = [i for i, c in enumerate(bm.chunks) if c.hash in have]
    dims = {have[bm.chunks[i].hash].shape[0] for i in rows}
    if len(dims) > 1:  # a model change mid-way: keep the most common size
        common = max(dims, key=lambda d: sum(have[bm.chunks[i].hash].shape[0] == d for i in rows))
        rows = [i for i in rows if have[bm.chunks[i].hash].shape[0] == common]
    mat = np.stack([have[bm.chunks[i].hash] for i in rows]) if rows else np.zeros((0, 1), dtype=np.float32)
    _matrix = (key, np.asarray(rows, dtype=np.int64), mat)
    if len(rows) < len({c.hash for c in bm.chunks}):
        documents.start_embedding()  # a new passage (an uploaded file, an edited SOP): embed it in the background
    return _matrix[1], _matrix[2]


def search(query: str, k: int = 4, text_cap: int = config.ASSISTANT_TEXT_CAP) -> list[dict]:
    """Best passages for `query`: BM25 and (when an embedding model is set) vector similarity, merged by reciprocal rank."""
    bm = index()
    pool = max(k * 4, 20)
    kw = bm.rank(query, pool)
    sem: list[tuple[float, int]] = []
    model = documents.embedding_model()
    if model:
        rows, mat = _vectors(bm, model)
        qv = documents.query_vector(query) if len(rows) else None
        if qv is not None and mat.shape[1] == qv.shape[0]:
            sims = mat @ qv
            top = np.argsort(-sims)[:pool]
            sem = [(float(sims[j]), int(rows[j])) for j in top]
    fused: dict[int, float] = {}
    for ranking in (kw, sem):
        for r, (_, i) in enumerate(ranking):
            fused[i] = fused.get(i, 0.0) + 1.0 / (60 + r + 1)
    kw_ids, sem_ids = {i for _, i in kw}, {i for _, i in sem}
    best = sorted(fused, key=lambda i: -fused[i])[:k]
    out = []
    for i in best:
        c = bm.chunks[i]
        match = "both" if i in kw_ids and i in sem_ids else "keyword" if i in kw_ids else "meaning"
        out.append({"source": c.source, "section": c.section, "text": c.text[:text_cap], "score": round(fused[i] * 1000, 1), "match": match, **({"doc_id": c.doc_id} if c.doc_id else {})})
    return out
