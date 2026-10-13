"""Contract check for a hosted OpenAI-style embedding model behind the LiteLLM gateway (e.g. text-embedding-3-large).

    python backend/tests/embedding_contract_smoke.py [model-id]

Serves a strict stand-in for the gateway's POST /v1/embeddings: the given model id, 3,072-dimension vectors in
LiteLLM's response shape, at most 16 inputs per request, empty strings and inputs over 8,191 tokens refused, and a
429 (with Retry-After) on the first call. Then embeds the app's whole document library through services/documents.py
and runs hybrid searches. It checks our side of the contract, not the quality of the real model's vectors. Uses a
throwaway data dir; never touches data/ or the real gateway.
"""
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(tempfile.gettempdir()) / "sentinel_embed_contract"
shutil.rmtree(DATA, ignore_errors=True)
os.environ["SENTINEL_DATA_DIR"] = str(DATA)
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402
from fastapi import FastAPI, Header, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from app.assistant import knowledge, settings as llm  # noqa: E402
from app.services import documents  # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "maas-text-embedding-3-large"
DIM, MAX_INPUTS, MAX_TOKENS, KEY = 3072, 16, 8191, "sk-contract"
seen = {"calls": 0, "inputs": 0, "max_batch": 0, "rejected_batches": 0, "rate_limited": 0}
gw = FastAPI()


def vec(text: str) -> list[float]:
    rng = np.random.default_rng(abs(hash(text.lower())) % (2**32))
    words = set(text.lower().split())
    v = rng.normal(size=DIM) * 0.05
    for w in words:  # shared words pull vectors together, so related passages are close
        v += np.random.default_rng(abs(hash(w)) % (2**32)).normal(size=DIM)
    return (v / np.linalg.norm(v)).round(6).tolist()


@gw.post("/v1/embeddings")
async def embeddings(request: Request, authorization: str | None = Header(None)):
    seen["calls"] += 1
    if authorization != f"Bearer {KEY}":
        return JSONResponse({"error": {"message": "Authentication Error", "type": "auth_error", "code": "401"}}, 401)
    if seen["calls"] == 1:
        seen["rate_limited"] += 1
        return JSONResponse({"error": {"message": "Rate limit reached", "code": "429"}}, 429, headers={"retry-after": "1"})
    body = await request.json()
    if body.get("model") != MODEL:
        return JSONResponse({"error": {"message": f"Invalid model name passed in model={body.get('model')}", "code": "400"}}, 400)
    inp = body["input"] if isinstance(body["input"], list) else [body["input"]]
    if len(inp) > MAX_INPUTS:
        seen["rejected_batches"] += 1
        return JSONResponse({"error": {"message": f"Too many inputs. The max number of inputs is {MAX_INPUTS}.", "code": "400"}}, 400)
    for t in inp:
        if not isinstance(t, str) or not t.strip():
            return JSONResponse({"error": {"message": "'$.input' is invalid. Please check the API reference", "code": "400"}}, 400)
        if len(t) / 4 > MAX_TOKENS:
            return JSONResponse({"error": {"message": f"This model's maximum context length is {MAX_TOKENS} tokens", "code": "400"}}, 400)
    seen["inputs"] += len(inp)
    seen["max_batch"] = max(seen["max_batch"], len(inp))
    return {"object": "list", "model": MODEL, "data": [{"object": "embedding", "index": i, "embedding": vec(t)} for i, t in enumerate(inp)],
            "usage": {"prompt_tokens": sum(len(t) // 4 for t in inp), "total_tokens": sum(len(t) // 4 for t in inp)}}


def check(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + ("" if ok else f" -> {str(detail)[:300]}"), flush=True)
    assert ok, name


with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
threading.Thread(target=uvicorn.Server(uvicorn.Config(gw, host="127.0.0.1", port=port, log_level="warning")).run, daemon=True).start()
time.sleep(1.5)
llm.save(llm.LlmSettings(base_url=f"http://127.0.0.1:{port}", api_key=KEY, model="chat-model", embedding_model=f" {MODEL} "))
print(f"stand-in gateway for {MODEL}: {DIM} dims, max {MAX_INPUTS} inputs/request, 429 on the first call")

# a document with one 30,000-character 'word' (a table pasted without spaces): must be trimmed, not refused
long_doc = DATA / "docs" / "upload_tmp"
long_doc.parent.mkdir(parents=True, exist_ok=True)
long_doc.write_text("# Price list\n" + "SKU|PRICE|" * 3000, encoding="utf-8")
documents.add(long_doc, "price-list.md", "reference")
time.sleep(0.2)
for _ in range(600):
    if not documents.embed_status()["running"]:
        break
    time.sleep(0.2)
st = documents.embed_status()
passages = {c.hash for c in knowledge.index().chunks}
have = documents.cached_vectors(MODEL, list(passages))
print(f"  gateway saw {seen['calls']} calls, {seen['inputs']} inputs, largest accepted batch {seen['max_batch']}, {seen['rejected_batches']} batches split, {seen['rate_limited']} rate limits")
check("the model id is sent trimmed and accepted", not st["error"], st)
check("every passage of the library embedded (incl. the 30k-char one)", len(have) == len(passages), (len(have), len(passages)))
check("vectors are 3,072-d, unit length", all(v.shape == (DIM,) for v in have.values()) and abs(float(np.linalg.norm(next(iter(have.values())))) - 1) < 1e-4)
check("indexing never sends more than the 16-input limit", seen["rejected_batches"] == 0 and seen["max_batch"] <= MAX_INPUTS, seen)
v40 = documents.embed([f"passage number {i} about stock" for i in range(40)], timeout=20)
check("a batch the gateway refuses is split and still returns every vector", v40.shape == (40, DIM) and seen["rejected_batches"] >= 1, (v40.shape, seen))
check("the 429 was retried, not fatal", seen["rate_limited"] == 1)

hits = knowledge.search("escalate suspected internal theft", k=5)
check("hybrid search uses the vectors", any(h["match"] in ("meaning", "both") for h in hits), hits)
check("a blank query is never sent to the gateway", documents.query_vector("   ") is None)
t0 = time.time()
knowledge.search("what does the store manager do about till fraud", k=4)
check("query embedding is quick", time.time() - t0 < 3)
size_mb = len(have) * DIM * 4 / 1e6
print(f"  storage: {len(have)} passages x {DIM} dims = {size_mb:.1f} MB of vectors in knowledge.sqlite")
print("EMBEDDING CONTRACT OK")
shutil.rmtree(DATA, ignore_errors=True)
