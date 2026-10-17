# Architecture Decision Records

## ADR-001: Deterministic finance engine, not the LLM
**Decision.** All authoritative financial arithmetic lives in
`src/finance/metrics.py`. The LLM may explain and synthesise, never compute.
**Why.** Correctness, auditability, and provenance. Each result carries its
formula, inputs, source references, and warnings (zero/negative denominators,
mixed basis, missing inputs). **Consequence.** Numbers are reproducible and
testable (`tests/unit/test_metrics.py`).

## ADR-002: Qdrant as default vector store (embedded)
**Decision.** Qdrant embedded on-disk by default; server mode optional.
**Why.** No mandatory Docker, strong metadata filtering, hybrid-ready,
scales to self-host/cloud. **Consequence.** Single-process lock in embedded
mode (documented); switch to server mode for concurrent access.

## ADR-003: Graceful degradation over hard dependencies
**Decision.** Docling, sentence-transformers, CrewAI and the cloud LLM are
optional at runtime. **Why.** The 16 GB / "no multi-GB weights" / offline-
friendly constraints. **Consequence.** The app runs with a pdfplumber parser,
a hashing embedder, a deterministic agent orchestrator and evidence-only
answers when those extras or the LLM key are absent — and says so in the UI.

## ADR-004: Manual-first ingestion; no scraping of access-controlled sites
**Decision.** Ship provider interfaces + a manual adapter; do not scrape
NSE/BSE/Screener. **Why.** Terms/access controls and the no-fabrication rule.
**Consequence.** Users upload or supply official URLs; compliant adapters can
be added later. See `docs/data_sources.md`.

## ADR-005: Physical PDF page vs printed page label kept distinct
**Decision.** `ChunkMetadata` stores `page_number` (physical index) separately
from `page_label` (printed). **Why.** They often differ in annual reports;
conflating them produces wrong citations. **Consequence.** Citations prefer the
printed label when known and fall back to the physical page, labelled as such.
