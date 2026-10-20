# Supply Chain Blast Radius Engine (GraphRAG)

Answers: *"Event X occurred at entity/location Y — which SKUs are exposed,
through what path, how much revenue is at risk, and with what confidence?"*

**Status: Phase 3 complete** (scaffold + data generator + dual-track
ingestion). LLM-driven extraction, entity resolution, graph build,
retrieval, eval, and UI are not yet written. Later-phase `make` targets
exit non-zero with a clear `[not yet implemented] ... lands in Phase <n>`
message.

Phase 3 adds the ingest pipeline. Run with services up:

```bash
make services                    # Qdrant + Neo4j via docker compose
ollama pull bge-m3               # local embeddings
# ... copy files from generated_data/ into data/inbox/
make ingest                      # or: python -m cli ingest
```

Pipeline (see `src/ingest/pipeline.py`):

- **File router by extension** (`src/ingest/router.py`) splits PDFs,
  DOCX, MD, TXT → narrative; XLSX, CSV, TSV → numeric; JSON, XML →
  structured; PNG/JPG → image track (deferred to Phase 4 vision pass).
- **Narrative track** writes markdown to `data/processed/narrative/`,
  chunks it (~1200 chars with 150 overlap, sentence-boundary trimmed),
  embeds each chunk via local Ollama (bge-m3), and upserts into Qdrant.
- **Numeric track** writes typed Parquet to `data/processed/numeric/`
  using pyarrow directly (bypasses pandas 3.0 API surface uncertainty).
  Each Parquet gets a sibling Markdown data card — schema, dtypes,
  provenance, sample rows — which is what Qdrant actually indexes.
  Phase 5 agents will search cards, then DuckDB-query the Parquet.
- **PDF table confidence check** (`src/ingest/tables.py`): primary
  extractor pdfplumber + independent secondary camelot. Overlap of
  normalised cell sets (Jaccard) becomes the confidence score. Below
  `table_confidence_floor` (default 0.75 from `config/settings.yaml`),
  the table **degrades to a narrative pipe-table block** instead of
  pretending to be structured data. If camelot can't be imported
  (missing ghostscript/opencv), pdfplumber runs solo with confidence
  capped at 0.80 and the audit log records `camelot unavailable`.
- **Gold tables** (`src/ingest/gold.py`): verified by sha256 at load
  time, copied into the processed tree at confidence 1.0 and
  `extraction_method=manual`. Checksum mismatch is a hard error.
- **Audit log** (SQLite at `data/processed/audit.sqlite`): one row per
  extraction attempt — file, sha, track, extractor, confidence, ok,
  note, rows/chars. Reruns consult it to skip files already processed
  for the same content hash. `--force` re-processes everything.
- **Resumable**: `python -m cli ingest` safely re-runs; use `--no-qdrant`
  to process to disk when the index service isn't up.

Measured on the Phase 2 corpus (173 files staged into `data/inbox/`,
Qdrant disabled): 9.7s, zero failures. Breakdown: 76 PDFs → narrative at
0.90, 80 PDF tables → numeric at 0.80 (pdfplumber-only ceiling, camelot
not installed in test env), 40 Excel sheets → numeric at 1.00, 24 DOCX →
narrative at 0.95, 14 CSV → numeric at 1.00, 30 plaintext → narrative at
1.00, 4 JSON + 1 XML → structured at 0.95 / 0.80.

---

## Architecture at a glance

**Dual-track ingestion.** Narrative text (contracts, news, audit PDFs,
emails) → Markdown → chunked → Qdrant → LLM relation extraction → graph
edges. Numeric data (Excel, CSV, financials, time series) → Parquet,
typed, never Markdown. Every numeric asset also emits a tiny Markdown
*data card* that is embedded; semantic search finds the card, the agent
runs real SQL against the Parquet file via DuckDB. A number enters the
numeric track **only** if extraction confidence clears a threshold —
otherwise it degrades to narrative text. This rule is the main defence
against bad table parsing.

**Graph.** Neo4j Community 5.26 LTS. Fixed node and relation vocabulary
(see `config/settings.yaml`). Every edge carries `confidence`,
`valid_from` / `valid_to`, `source_ref`, and `extraction_method`. Schema
is enforced deterministically at write time.

**Retrieval.** A deterministic router — not an agent — classifies each
query as semantic / structural / quantitative (usually all three),
decomposes, dispatches to Qdrant / Neo4j / DuckDB, and recombines.
CrewAI is reserved for the two places agents actually help: ingestion
crew (parser → extractor → resolver → validator) and tier-2 inference
crew (researcher → corroborator → confidence-scorer).

**UI.** Phase 8. React Three Fiber, layered DAG with hierarchical edge
bundling, bloom pass, offline-computed layout, Ambient + Query states.

For the full rationale and risk mitigations (table extraction, entity
resolution with a non-destructive mapping layer and review CLI, tier-2
inference as hypotheses with structural-evidence scoring, constrained
structured LLM output, propose-and-verify), read the design brief that
seeded this repo.

---

## Pinned versions (verified against PyPI / Docker Hub on 2026-10-20)

| Component | Version | Why pinned |
|---|---|---|
| Neo4j (server) | `5.26.32-community` | 5.x LTS line, patched |
| Neo4j (driver) | `6.4.1` | 6.x driver intentionally decoupled from 5.x server; API shifted from 5.x driver line |
| Qdrant (server) | `v1.19.2` | must match client major |
| qdrant-client | `1.19.1` | lockstep with server |
| CrewAI | `1.15.28` | 1.x line; verify import surface at setup (see "To verify" below) |
| Ollama Python | `0.6.3` | |
| DuckDB | `1.5.6` | stable 1.x line |
| pandas | `3.0.6` | **3.x: CoW default, 2.x APIs removed** |
| pyarrow | `26.0.0` | |
| pdfplumber | `0.11.10` | first PDF-table extractor |
| camelot-py | `2.0.0` | second extractor (disagreement signal) |
| unstructured | `0.27.30` | |
| python-docx | `1.2.0` | |
| openpyxl | `3.1.5` | |
| rapidfuzz | `3.14.6` | ER string signal |
| networkx | `3.7` | |
| FastAPI | `0.151.0` | API (Phase 7) |
| uvicorn | `0.54.0` | |
| typer | `0.27.3` | CLI |
| httpx | `0.28.1` | |
| pydantic | `2.14.1` | |
| ruff | `0.17.1` | dev |
| pytest | `9.1.1` | dev |
| faker | `40.43.0` | datagen extra |

### To verify at setup (I could not reach these hosts from this build)

1. **Ollama Cloud model catalog.** Pick an extraction model and (optional)
   verifier model, write them into `.env`. Likely candidates are
   `llama3.1:70b` or `qwen2.5:72b` but confirm what's actually offered.
2. **`bge-m3` embedding dimension.** The `.env.example` assumes 1024.
   Confirm with `ollama show bge-m3` before Phase 4 creates the Qdrant
   collection — the dim is baked in and changing it later means a reindex.
3. **CrewAI 1.15 import surface.** After `pip install`, check that
   `from crewai import Agent, Task, Crew, Process` still works. The 0.x →
   1.x jump may have moved things.

Honest about what I don't know rather than inventing values.

---

## Repository layout

```
data/
  inbox/               # YOU drop files here. Empty on delivery.
  gold/                # hand-verified critical tables (see data/gold/README.md)
  processed/
    narrative/         # .md chunks
    numeric/           # .parquet + .md data cards
  graph/               # built graph + precomputed layout file for the UI
src/
  ingest/   extract/   resolve/   graph/   index/
  retrieve/ agents/    api/
ui/                    # React Three Fiber (Phase 8)
tools/datagen/         # STANDALONE generator — ruff + a test enforce no src/ imports
eval/                  # Phase 6: comparison vs vector-RAG baseline
tests/
config/                # settings.yaml, aliases.yaml, extraction_schema.json
cli/                   # typer app: ingest, build-graph, query, review-merges, unmerge
docker-compose.yml     # Qdrant + Neo4j
Makefile
pyproject.toml
.env.example
```

---

## Getting running (Phase 1 — what works today)

```bash
make setup                           # creates .venv, installs deps
cp .env.example .env && $EDITOR .env # fill NEO4J_PASSWORD at minimum
make services                        # docker compose up Qdrant + Neo4j
make test                            # Phase 1 tests pass: config shape, datagen boundary
make lint                            # ruff
```

Qdrant dashboard at <http://localhost:6333/dashboard>, Neo4j Browser at
<http://localhost:7474>.

Phase 2+ targets (`make generate-data`, `make ingest`, `make build-graph`,
`make eval`, `make dev`) exist and are wired, but exit non-zero until
their phases land.

---

## Build phases

1. Scaffold + docker-compose + config + CLI skeleton + README.
2. Standalone data generator → `generated_data/` (apparel/fast-fashion).
3. **Dual-track ingestion + parsers + confidence routing.** ← we are here
4. Extraction → entity resolution → graph build → Qdrant index
5. Hybrid retrieval router + CrewAI crews
6. **Evaluation harness + baseline comparison — must pass before UI**
7. API layer (FastAPI)
8. 3D UI (React Three Fiber)

Each phase ends with a confirmation checkpoint before the next starts.

---

## Scope boundaries (what this project is NOT)

- No live ERP integration
- No procurement execution
- No real customs or shipping-manifest data
- No multi-tenant auth
- No SLA guarantees — it's a research/analysis engine, not a production
  monitoring tool

---

## Reported measurements

**Empty by design in Phase 1.** Phase 6 fills in: retrieval precision,
path correctness, hallucination rate, latency, cost per query, and ER
precision/recall/F1 on a labelled 200-pair set. Failures reported alongside
successes — measured risk is credibility.

---

## Author

Shivika Khanna · PGDM Business Data Analytics, FORE School of Management.
Project repo: [github.com/anonymous-2924/shivikak-24](https://github.com/anonymous-2924/shivikak-24).
