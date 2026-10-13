"""Small documentation knowledge base with BM25 search (no embeddings dependency)."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app import config
from app.assistant import plain_language

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
            chunks.append(Chunk(source=source, section=section, text=part, tokens=tokenize(section + " " + part)))

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

    def search(self, query: str, k: int = 4) -> list[tuple[float, Chunk]]:
        q = tokenize(query)
        if not q:
            return []
        scored = [(self.score(q, i), c) for i, c in enumerate(self.chunks)]
        scored = [sc for sc in scored if sc[0] > 0]
        scored.sort(key=lambda x: -x[0])
        return scored[:k]


_index: tuple[tuple[float, ...], BM25] | None = None


def _signature() -> tuple[float, ...]:
    sops_dir = config.SOPS_DIR
    sop_sig = sum(p.stat().st_mtime for p in sops_dir.glob("*.md")) if sops_dir.exists() else -1.0
    return tuple(p.stat().st_mtime if p.exists() else -1.0 for _, p in DOCS) + (sop_sig,)


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
    _index = (sig, BM25(chunks))
    return _index[1]


def search(query: str, k: int = 4, text_cap: int = config.ASSISTANT_TEXT_CAP) -> list[dict]:
    hits = index().search(query, k)
    return [{"source": c.source, "section": c.section, "text": c.text[:text_cap], "score": round(s, 2)} for s, c in hits]
