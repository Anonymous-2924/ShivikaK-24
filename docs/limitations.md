# Limitations & What Is / Isn't Verified

## Verified in this build (tests pass locally, Python 3.13)
- Deterministic finance engine with provenance (`tests/unit/test_metrics.py`).
- File validation, safe filenames/path-traversal guard, SHA-256 dedup.
- Structure-aware chunking; table chunks kept whole.
- Citations + grounding checks (quote/number verification); abstention.
- Hybrid retrieval (real BM25 + RRF fusion) and metadata filtering.
- SQLite metadata/chunk stores with idempotent upsert.
- End-to-end: parse → chunk → embed (hashing) → index (embedded Qdrant) →
  retrieve → cite, including **persistence across restart** and idempotent
  re-index (`tests/integration/`).
- PDF parsing via PyMuPDF (default, fast) and pdfplumber (fallback) on a real PDF fixture, with per-page progress.
- Ollama client error mapping (auth/rate-limit/unavailable) via mocks.
- Streamlit app boots and serves all 7 pages (HTTP 200).

## NOT verified / requires external configuration
- **Ollama Cloud generation** — needs a real `OLLAMA_API_KEY`. The client is
  implemented against the documented Ollama REST shape; **confirm the exact
  Cloud auth/endpoint/model identifiers against current official docs** for
  your account. `scripts/smoke_test.py` exercises it when a key is present.
- **Docling parsing** — optional; pulls PyTorch + models (large). Not
  auto-installed on a 16 GB machine. PyMuPDF (fast, CPU-only) is the working default parser; pdfplumber is the fallback.
- **Local semantic embeddings / reranker** — need `sentence-transformers`
  (one-time ~80 MB download). Without it, the hashing fallback is used (weaker
  semantics; clearly labelled).
- **CrewAI LLM-driven crew** — needs `crewai` + a working LLM. Without them, a
  deterministic fallback orchestrator runs the same stages (no fabricated crew).
- **MinerU comparison** — optional, heavy; not wired to execute in this build.
- **Official-source auto-discovery (NSE/BSE/Screener)** — intentionally not
  shipped (access controls/terms). Manual upload/URL is the supported path.
- **OCR for scanned PDFs** — flagged, not performed (needs Docling/Tesseract).

## Security posture
Environment-based secrets, secret redaction in logs, SSRF-guarded downloads,
size/type/timeout limits, document text treated as untrusted (prompt-injection
guard in the system prompt), no execution of document content. This is **not**
a production security review — do not deploy publicly without one.
