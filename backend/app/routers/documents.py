"""Document library: upload SOPs and reference documents for the assistant, see what is indexed, test what it finds."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import config
from app.assistant import knowledge
from app.routers.common import stream_upload
from app.services import documents, sops, storage

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _builtin() -> list[dict[str, Any]]:
    """What the assistant reads without any upload: the guide, README, story, glossary and the built-in SOPs."""
    idx = knowledge.index()
    uploaded_sops = {d["sop_id"] for d in documents.list_documents() if d["kind"] == "sop"}
    counts: dict[str, int] = {}
    for c in idx.chunks:
        if c.doc_id is None:
            counts[c.source] = counts.get(c.source, 0) + 1
    out = []
    for name, n in counts.items():
        if name.startswith("SOP "):
            continue
        out.append({"name": name, "kind": "guide", "n_chunks": n})
    built_in_sops = [s for s in sops.load().values() if s.id not in uploaded_sops]
    out.append({"name": f"{len(built_in_sops)} built-in SOPs", "kind": "sop", "n_chunks": sum(counts.get(f"SOP {s.id}", 0) for s in built_in_sops)})
    return out


@router.get("")
def list_documents() -> dict[str, Any]:
    idx = knowledge.index()
    model = documents.embedding_model()
    embedded = 0
    if model:
        hashes = list({c.hash for c in idx.chunks})
        embedded = len(documents.cached_vectors(model, hashes))
        total = len(hashes)
    else:
        total = len({c.hash for c in idx.chunks})
    return {
        "documents": documents.list_documents(),
        "builtin": _builtin(),
        "index": {
            "passages": total, "embedded": embedded, "embedding_model": model or None,
            "mode": "hybrid" if model and embedded else "keyword", **{k: v for k, v in documents.embed_status().items() if k != "model"},
        },
        "limits": {"max_mb": config.DOC_MAX_MB, "types": list(config.DOC_TYPES)},
    }


@router.post("")
async def upload(file: UploadFile = File(...), kind: str = Form("auto")) -> dict[str, Any]:
    if kind not in ("auto", "sop", "reference"):
        raise HTTPException(400, "kind must be auto, sop or reference.")
    config.ensure_dirs()
    tmp = config.DOCS_DIR / f"upload_{storage.new_id('tmp')}"
    await stream_upload(file, tmp)
    try:
        return documents.add(tmp, file.filename or "document.txt", kind)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/search")
def search(q: str, k: int = 5) -> dict[str, Any]:
    """The passages the assistant's search_docs tool would get for this question."""
    return {"hits": knowledge.search(q, k=max(1, min(k, 10)), text_cap=500), "mode": "hybrid" if documents.embedding_model() else "keyword"}


@router.post("/reindex")
def reindex() -> dict[str, Any]:
    """Embed every passage that has no vector yet for the current embedding model (e.g. after changing the model)."""
    if not documents.embedding_model():
        raise HTTPException(400, "Choose an embedding model in Settings first; until then search is keyword-only.")
    return {"started": documents.start_embedding(), **documents.embed_status()}


@router.get("/{doc_id}")
def get_document(doc_id: str) -> dict[str, Any]:
    return {**documents.get(doc_id), "preview": documents.preview(doc_id)}


@router.get("/{doc_id}/file")
def download(doc_id: str) -> FileResponse:
    doc = documents.get(doc_id)
    path = documents.original_path(doc)
    if not path.exists():
        raise HTTPException(404, "The original file is no longer on disk.")
    return FileResponse(path, filename=doc["name"])


@router.delete("/{doc_id}")
def delete(doc_id: str) -> dict[str, bool]:
    return {"deleted": documents.delete(doc_id)}
