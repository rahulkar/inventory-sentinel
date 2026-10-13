"""Document library smoke: upload SOPs and reference documents, keyword then hybrid (embedding) search, delete.

    SENTINEL_SMOKE_DIR=%TEMP%\\docs_smoke python backend/tests/documents_smoke.py

Runs against a throwaway data dir (wiped first) and the fake gateway (tests/fake_gateway.py, which serves hashed
bag-of-words embeddings as "fake-embed"), so it needs no network and never touches data/ or the real gateway.
"""
import os
import shutil
import socket
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("SENTINEL_SMOKE_DIR") or Path(tempfile.gettempdir()) / "sentinel_docs_smoke")
shutil.rmtree(DATA, ignore_errors=True)
os.environ["SENTINEL_DATA_DIR"] = str(DATA)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

import fake_gateway  # noqa: E402
from app.assistant import knowledge, settings as llm  # noqa: E402
from app.main import app  # noqa: E402
from app.services import documents, sops  # noqa: E402


def check(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + ("" if ok else f" -> {str(detail)[:400]}"), flush=True)
    assert ok, name


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def tiny_pdf(text: str) -> bytes:
    """A one-page PDF with `text` in Helvetica (enough for pypdf to extract)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def tiny_docx(heading: str, paras: list[str]) -> bytes:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{heading}</w:t></w:r></w:p>' + "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
    path = Path(tempfile.mkdtemp()) / "x.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {w}><w:body>{body}</w:body></w:document>')
    return path.read_bytes()


SOP = """---
id: cash-office-check
title: Cash office spot check
version: 2
applies_to: [scan_fraud]
owner_role: Store manager
summary: Count the tills and reconcile voids when till fraud is suspected.
steps:
  - id: s1
    text: Count every till drawer against the Z-read before the shift ends.
    role: Store manager
    due_hours: 4
  - id: s2
    text: Pull the void and override log for the flagged days.
    role: Loss prevention
    due_hours: 24
---
Keep the evidence for 90 days.
"""

c = TestClient(app)

# ---- keyword-only (no embedding model)
r = c.get("/api/documents").json()
check("library lists the built-in guide and SOPs", any(b["kind"] == "sop" for b in r["builtin"]) and r["index"]["mode"] == "keyword", r)
n_sops = len(sops.load())

r = c.post("/api/documents", files={"file": ("cash-office.md", SOP.encode(), "text/markdown")}, data={"kind": "auto"})
check("Markdown with SOP front matter becomes a live SOP", r.status_code == 200 and r.json()["kind"] == "sop" and "cash-office-check" in sops.load() and len(sops.load()) == n_sops + 1, r.text)
sop_doc = r.json()["id"]
r = c.post("/api/documents", files={"file": ("bad-sop.md", b"# just a heading\nno front matter", "text/markdown")}, data={"kind": "sop"})
check("a file without SOP front matter is refused as an SOP", r.status_code == 400 and "front matter" in r.json()["detail"], r.text)

policy = "# Returns policy\n## Refund limits\nStores may refund up to 250 pounds without a receipt; above that the regional manager approves.\n## Damaged stock\nDamaged stock is written off with reason code DMG and photographed."
r = c.post("/api/documents", files={"file": ("returns-policy.md", policy.encode(), "text/markdown")})
check("Markdown without front matter becomes a reference document", r.status_code == 200 and r.json()["kind"] == "reference" and r.json()["n_chunks"] == 2, r.text)
r = c.post("/api/documents", files={"file": ("returns-copy.md", policy.encode(), "text/markdown")})
check("the same content twice is recognised as a duplicate", r.json().get("duplicate") is True, r.text)
r = c.post("/api/documents", files={"file": ("security.pdf", tiny_pdf("Security tags must be removed only at the till by trained staff"), "application/pdf")})
check("PDF text is extracted", r.status_code == 200 and r.json()["n_chunks"] == 1, r.text)
pdf_doc = r.json()["id"]
r = c.post("/api/documents", files={"file": ("stocktake.docx", tiny_docx("Stocktake rules", ["Full stocktake twice a year.", "Cycle counts weekly for high theft risk items."]), "application/octet-stream")})
check("Word text and headings are extracted", r.status_code == 200 and r.json()["n_chunks"] == 1, r.text)
r = c.post("/api/documents", files={"file": ("notes.xlsx", b"PK\x03\x04junk", "application/octet-stream")})
check("unsupported types are refused", r.status_code == 400, r.text)

hits = c.get("/api/documents/search", params={"q": "refund without a receipt"}).json()["hits"]
check("keyword search finds the uploaded policy", hits and hits[0]["source"] == "returns-policy.md" and hits[0]["match"] == "keyword", hits)
hits = knowledge.search("count till drawers Z-read", k=3)
check("the uploaded SOP is searchable as an SOP", any(h["source"] == "SOP cash-office-check" for h in hits), hits)

# ---- hybrid: point the gateway settings at the fake gateway with an embedding model
port = free_port()
fake_gateway.serve_in_thread(port)
time.sleep(1.0)
llm.save(llm.LlmSettings(base_url=f"http://127.0.0.1:{port}", api_key=fake_gateway.API_KEY, model=fake_gateway.MODEL, embedding_model=fake_gateway.EMBED_MODEL))
check("reindex starts", c.post("/api/documents/reindex").json()["started"] is True)
for _ in range(100):
    if not documents.embed_status()["running"]:
        break
    time.sleep(0.2)
st = c.get("/api/documents").json()["index"]
check("every passage embedded", st["embedded"] == st["passages"] and st["mode"] == "hybrid" and not st["error"], st)

hits = knowledge.search("shoplifting stolen goods", k=5)  # the fake embedder maps stolen/shoplifting -> theft
check("meaning-only matches come through the vector side", any(h["match"] in ("meaning", "both") for h in hits), hits)
hits = knowledge.search("refund without a receipt", k=3)
check("exact keywords still rank first in hybrid mode", hits[0]["source"] == "returns-policy.md" and hits[0]["match"] == "both", hits)

# gateway gone: search falls back to keywords instead of failing
llm.save(llm.LlmSettings(base_url="http://127.0.0.1:9", api_key="x", model="m", embedding_model="fake-embed"))
documents._qcache.clear()
t0 = time.time()
hits = knowledge.search("damaged stock write off", k=3)
check("a dead gateway falls back to keyword search", hits and hits[0]["source"] == "returns-policy.md" and time.time() - t0 < 10, hits)

# ---- delete
check("delete a reference document", c.delete(f"/api/documents/{pdf_doc}").json()["deleted"] and not any(h["source"] == "security.pdf" for h in knowledge.search("security tags till", k=5)))
check("delete an uploaded SOP", c.delete(f"/api/documents/{sop_doc}").json()["deleted"] and "cash-office-check" not in sops.load())
print("ALL DOCUMENT CHECKS PASSED")
