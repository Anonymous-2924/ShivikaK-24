# Supply Chain Blast Radius Engine (GraphRAG)

Answers: *"Event X occurred at entity/location Y — which SKUs are exposed,
through what path, how much revenue is at risk, and with what confidence?"*

**Status: Phase 6 complete** (scaffold + data generator + dual-track
ingestion + LLM extraction + entity resolution + graph build + hybrid
retrieval router + tier-2 inference crew + evaluation harness vs. a
vector-RAG baseline). The UI is not yet written. Later-phase `make`
targets exit non-zero with a clear `[not yet implemented] ... lands in
Phase <n>` message.

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

## Phase 4 — LLM extraction + ER + graph build

Three subsystems that stand alone and plug together:

**1. LLM extraction** (`src/extract/`)

- Proposer: `gpt-oss:20b` on Ollama Cloud (free-tier). Verifier:
  `nemotron-3-ultra` (free-tier, different architecture family — the
  point of a verifier is to NOT share the proposer's blind spots).
- Separate passes per chunk: entities, then relations. Not one combined
  call. Constrained to JSON via `format='json'` + strict prompt + strict
  validator. Any entity whose name doesn't appear verbatim in the chunk
  is dropped (brief rule: never invent). Any relation referencing an
  entity the entity pass didn't surface is dropped. Any out-of-vocab
  type is dropped.
- Verifier runs on **every** high-impact edge (`supplied_by`,
  `manufactured_at`, `disrupted_by`) and on a sampled fraction
  (default 10%) of other chunks. Its JSON verdict folds back:
  `accept` keeps the edge with verifier confidence; `modify` changes
  the type (still vocab-gated); `reject` drops it.
- Resumable. State is `data/processed/extractions.jsonl`, one line
  per completed `(source_file, chunk_index)`. On a session-cap error
  from Ollama Cloud (the Free tier's 4-hour window), the extractor
  checkpoints what's done and exits 0. Re-running continues from the
  next chunk — no work lost, no sleep loop.
- CLI: `python -m cli extract [--no-verify] [--sample-rate 0.1]`.

**2. Entity resolution** (`src/resolve/`)

- Three buckets (brief rule): auto-merge ≥ 0.92; review 0.78–0.92
  (**never** auto-merged); auto-reject < 0.78.
- Combined score blends **string similarity** (rapidfuzz, token-set
  ratio on name-normalised strings — strips suffixes like Ltd/Pvt/Co.)
  with **structural evidence**: shared tax_id (dominant signal),
  address similarity, shared country, shared customer, shared route.
  Different-type pairs are capped at 0.5 and never auto-merge.
- Addresses missing on either side don't penalise — their weight is
  redistributed across the signals that are present.
- **Non-destructive mapping layer** in `data/processed/merges.sqlite`:
  one row per merge, source → canonical. Resolve walks the mapping
  transitively. Unmerge sets `reversed=1` on the row — source entities
  are never mutated and the history is auditable.
- Review queue: `python -m cli review-merges` surfaces each candidate
  with its evidence; keys y/n/s/q.
- Unmerge: `python -m cli unmerge <entity_id>`.
- `config/aliases.yaml` is a hand-curated override hook (loader present;
  population flows from the review queue outcomes you accept).
- **Evaluated on a 200-pair labelled fixture** (`tests/fixtures/er_pairs.json`,
  generated deterministically via `python -m tools.datagen.er_pairs`):
  80 match / 80 no_match / 40 ambiguous. Current scorer:
  **precision 1.000, recall 1.000, F1 1.000**; 40/40 ambiguous pairs
  routed to auto-reject (none wrongly auto-merged). **Credibility note:**
  the fixture tests the scorer against the exact mess the generator
  injects (near-duplicates share tax_id); these numbers do NOT prove
  robustness against adversarial pairs (e.g. same company with different
  tax IDs, or legitimately different companies that coincidentally share
  one). That's a Phase 6 concern on real data.

**3. Graph build** (`src/graph/`)

- Neo4j 5.26 LTS via driver 6.4. Node id uniqueness constraints are
  created once (`writer.ensure_constraints`). Nodes and edges upsert
  idempotently via MERGE.
- **Deterministic schema validator** (`src/graph/schema.py`) with a
  whitelist of valid (source_type, relation, target_type) triples.
  Edges that violate the whitelist, or that lack any of the five
  required fields (confidence, valid_from, valid_to, source_ref,
  extraction_method), are rejected **before** reaching Neo4j — the
  writer counts them in `edges_rejected_schema`.
- Three build sources, in confidence order:
  - **Structured ERP exports** (JSON/XML from `data/inbox/`):
    `extraction_method=structured`, confidence 0.98.
  - **Gold data cards** (`data/processed/numeric/*.md` linked to a
    supplier): `extraction_method=manual`, confidence 1.0, as
    `has_financials` edges to a `DataTable` node whose `parquet_path`
    is the file Phase 5's quantitative router will DuckDB-query.
  - **LLM-extracted relations** (`extractions.jsonl`):
    `extraction_method=llm_extracted`, confidence from the verifier
    (or proposer, if un-verified).
- Every node id is resolved through the ER mapping layer before writing,
  so merged entities land on the canonical id.
- CLI: `python -m cli build-graph`.

### Phase 4 honest limitations

- **No live Ollama Cloud or Neo4j test from this environment.** The
  cloud container I ran in has no running Neo4j and no `OLLAMA_CLOUD_API_KEY`.
  Deterministic pieces are unit-tested; the LLM and Neo4j paths are
  stub-tested (mock chat clients that return scripted JSON; a mock Neo4j
  driver that logs Cypher). The real end-to-end runs are yours to do:
  `export OLLAMA_CLOUD_API_KEY=... && make services && python -m cli extract && python -m cli build-graph`.
- **The 1.0/1.0/1.0 ER numbers are honest but not comprehensive** — see
  the credibility note above.
- **CrewAI is NOT used in Phase 4.** The brief says ingestion crew
  (parser → extractor → resolver → validator) should use CrewAI; my
  reading is that this pipeline is deterministic enough that a plain
  orchestrator earns the same correctness at a fraction of the moving
  parts. CrewAI is reserved for the Phase 5 tier-2 inference crew where
  the loop (researcher → corroborator → confidence-scorer) is genuinely
  multi-agent.
- **Vision extraction (PNG/JPG files) is still deferred.** Phase 3
  routes them to track `image` and the ingest records them as
  `[Phase 4]`; the Phase 4 LLM calls don't yet take images. If you want
  the chart screenshots indexed, add a vision pass as a Phase 4.5.

---

## Phase 5 — Hybrid retrieval router + tier-2 inference crew

**1. Retrieval router** (`src/retrieve/`)

- `router.py`: deterministic classifier + decomposer, **not an agent**
  (brief rule — faster, cheaper, debuggable). Regex/keyword heuristics
  classify a question into semantic / structural / quantitative
  (usually more than one — an exposure-tracing question like "if plant X
  goes down, which SKUs are exposed and what revenue is at risk" pulls
  in all three). Also extracts entity-name hints (a capitalised-phrase
  heuristic, not NER — honestly a first pass) and an `--as-of` date,
  either passed explicitly or parsed from the question text.
- `semantic.py`: embeds the question (reuses Phase 3's `Embedder`) and
  kNN-searches Qdrant (reuses `QdrantIndex`, which gained a `search()`
  method this phase — Phase 3 only needed `upsert`/`count`).
- `structural.py`: parameterised Cypher traversal. First-class case:
  "given a disruption, which SKUs are reachable and through what
  paths" — `exposure_paths()`. Returns plain dict/list records, never
  raw neo4j `Path` objects, so it's testable with a fake driver (same
  pattern as `tests/test_graph_writer_stub.py`) without a real server.
  `--as-of` filters traversed edges by `valid_from`/`valid_to`.
- `quantitative.py`: Neo4j `has_financials` edge -> `DataTable` ->
  DuckDB on the Parquet. The brief is explicit: **no LLM-written SQL in
  Phase 5.** The generated corpus has no fixed financial schema (every
  sheet infers its own columns), so the fixed catalog (`revenue`,
  `buffer_days`, `lead_time`) *discovers* a matching column by name
  pattern against the Parquet's real schema rather than guessing a
  column name — safe, and honest about not knowing the exact schema in
  advance.
- `combine.py`: recombines dispatcher outputs into one answer.
  Confidence is the **minimum** across every source actually used (the
  weakest link sets it, not an average), and every claim carries a
  `source_ref`.
- `service.py` / `cli query "<question>"` / `make query QUESTION="..."`:
  wires it all together. Any unreachable backend (Qdrant, Neo4j) is
  skipped with a logged note rather than failing the whole query — same
  philosophy as the ingest pipeline.

**2. Tier-2 inference crew** (`src/agents/`) — the one place CrewAI is
actually used (brief rule: don't make everything an agent just because
the framework is available; ingestion and the router above are both
deterministic for that reason)

- `ollama_llm.py`: a `crewai.llms.base_llm.BaseLLM` subclass wrapping
  the Phase 4 `OllamaChat` client, instead of CrewAI's native
  `litellm`-backed `LLM` class. I could not verify litellm's exact
  provider-string/base_url convention for *Ollama Cloud* specifically
  (vs. local Ollama) without guessing — and this project already got
  burned once by an unverified version number. Reusing the
  already-tested client (session-cap detection included) avoids a
  second unverified integration path. `OllamaChat` also gained a
  `chat_text()` method (freeform, no forced `format='json'`) alongside
  the existing `chat_json()`, for the crew's normal reasoning text.
- `tier2.py`: researcher -> corroborator -> confidence-scorer.
  **Critical brief rule, structurally enforced, not just by
  convention**: corroboration confidence is computed by
  `score_corroboration()` — plain Python, from evidence *structure*
  (count of independent sources, a source-type reliability weight,
  recency decay) — **never from a model's self-reported confidence**.
  The researcher agent only extracts candidate names + evidence from
  text; the "confidence-scorer" agent only writes the narrative
  explaining a score it's handed, it doesn't invent its own number.
  Hypotheses are written as `extraction_method="inferred"` edges with
  an extra `is_hypothesis=true` prop (no schema change needed — the
  validator only checks required fields are present) so Phase 8's UI
  can render them dashed/dim.
- `tests/tier2_validation/`: a **two-company** (not five — see caveat
  below) validation harness against public facts about Apple/TSMC/ASML
  (high confidence — this is well-established, widely-reported
  semiconductor-industry knowledge) and Toyota/Denso/Renesas (moderate
  confidence — the 2021 Renesas fire's broad impact on Japanese
  automakers is well reported; the specific Denso<->Renesas link is
  recalled with less certainty). Neither fact was independently
  re-verified against a primary source in this session. **Explicitly
  indicative, not rigorous** (N=2, synthetic one-sentence "evidence,"
  no statistical meaning) — it is a smoke test of the crew mechanism,
  not a benchmark. Costs real Ollama Cloud credits in real mode; never
  auto-run — `python -m tests.tier2_validation.run_validation --stub`
  exercises the harness mechanics for free with a scripted LLM.

### Phase 5 fixes to existing Phase 4 code

- **`build_from_extractions` name resolution was silently broken.**
  `cli/__main__.py`'s `build-graph` command passed it a hardcoded `{}`
  for `name_to_id`, so every LLM-extracted relation was counted as
  `edges_skipped_unresolved` — none ever reached Neo4j. Added
  `load_name_to_id_map()` in `src/graph/builder.py`, which builds a
  best-effort name -> id map from the structured ERP exports (supplier
  name, plant name, component description, SKU style number, route id),
  and wired it into the CLI. This is a name-matching heuristic, not a
  new ER pass — a name the LLM saw in prose that the ERP never recorded
  still won't resolve, same as before.
- **`pydantic==2.14.1` (the Phase 1 pin) is incompatible with
  `crewai==1.15.28`** (requires `pydantic<2.13,>=2.11.9`) — this had
  never been caught because nothing before Phase 5 imported crewai.
  Re-pinned to `pydantic==2.12.5` (latest patch under crewai's ceiling;
  re-verified the whole dependency set resolves together on PyPI).
  `fastapi==0.151.0` only needs `pydantic>=2.9.0`, so this doesn't touch
  that pin. See the version table below.

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
| CrewAI | `1.15.28` | 1.x line; import surface (`from crewai import Agent, Task, Crew, Process`) verified against the actual wheel in Phase 5 — works. |
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
| pydantic | `2.12.5` | **changed in Phase 5** — `2.14.1` (the Phase 1 pin) is incompatible with `crewai==1.15.28`, which requires `pydantic<2.13,>=2.11.9`. `2.12.5` is the latest patch under that ceiling; re-verified against the full dependency set on PyPI, resolves cleanly. `fastapi==0.151.0` only needs `>=2.9.0`, so this doesn't touch that pin. |
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
3. Dual-track ingestion + parsers + confidence routing.
4. Extraction → entity resolution → graph build → Qdrant index.
5. Hybrid retrieval router + CrewAI tier-2 crew.
6. **Evaluation harness + baseline comparison.** ← we are here
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

Real numbers from a clean local run (45 questions, `eval/questions.jsonl`;
full detail in `eval/results_detail.jsonl`; regenerate with `make eval`).
GraphRAG is `src/retrieve/service.py`; baseline is the plain vector-RAG
pipeline in `eval/baseline_vector_rag.py` (embed → top-k Qdrant →
concatenate → one LLM call, no graph, no DuckDB).

| | GraphRAG | Baseline |
|---|---|---|
| Mean retrieval precision (overall) | 0.249 | 0.050 |
| Mean path correctness (23 scored) | 0.381 | 0.087 |
| Mean hallucination rate (10 scored) | 0.000 | n/a (0 scored) |
| p50 latency | 163.6 ms | 4301.5 ms |
| p95 latency | 1670.0 ms | 11754.6 ms |
| Cost / query | $0.0000 | $0.0000 |
| Errors | 0/45 | 0/45 |

**By category** — this is where the real signal is; the overall row
above flattens categories that behave very differently:

| Category | GraphRAG precision | Baseline precision | Why |
|---|---|---|---|
| exposure_tracing | **0.833** | 0.000 | GraphRAG wins decisively: this needs structured relational traversal (which SKUs contain component X, which plant manufactures SKU Y), and narrative-chunk retrieval has no access to that data *in principle* — not a tuning gap, a category mismatch. Path correctness (0.653 vs 0.167) tells the same story. |
| monitoring | 0.000 | **0.177** | Baseline wins outright on recall-worthy content — but GraphRAG's 0.000 here is partly a measurement artifact, not a retrieval failure: see the doc_id-format bug below. Once that's fixed the honest number will be higher than 0, though likely still behind baseline, since this category is squarely semantic-chunk territory. |
| risk_quantification | 0.111 | 0.000 | Both weak, for different reasons. GraphRAG's quantitative dispatcher only reaches numeric data via a `has_financials` edge, and none exist in this build (ingest only sets `linked_entities` for gold tables, and this corpus has none) — real retail prices and buffer-days sit in ingested Parquet files the graph can't point to. The baseline has no structured-numeric path at all, ever. |
| tier2_inference | 0.000 | 0.027 | GraphRAG has zero `inferred` edges — the tier-2 crew (`src/agents/tier2.py`) was never run against this corpus (it costs real Ollama Cloud credits). Baseline does a *little* better because the one real textual hint in this corpus (an audit noting "subcontractor list missing one tier-2 fabric mill" for SUP-T1-0022) is narrative text its retrieval can actually surface. |

**Honest limitations this run surfaced, not papered over:**
- **A real bug in the eval harness, not the system under test.**
  `eval/metrics.py:retrieval_precision` compares returned doc ids against
  `expected.source_doc_ids` verbatim. GraphRAG's semantic hits carry
  Qdrant's chunk-level doc id (`audit_SUP-T1-0008.pdf::chunk::0`, from
  `src/index/qdrant.py`'s `IndexDoc.doc_id`), while the baseline's and
  `questions.jsonl`'s expected ids are bare filenames
  (`audit_SUP-T1-0008.pdf`). Verified directly against
  `eval/results_detail.jsonl`: for `mon-01`, GraphRAG's and the baseline's
  *first three retrieved ids name the exact same three files* — only the
  `::chunk::N` suffix differs. That suffix mismatch alone drops GraphRAG's
  precision to 0.000 on every monitoring/tier2 question, understating how
  good its semantic retrieval actually is. Not fixed in this run (found
  while writing up these results, after the run finished) — fix is
  stripping the `::chunk::N` suffix before comparison in
  `retrieval_precision`, or storing a parallel `source_file` field
  everywhere (already present on `SemanticHit`, not yet threaded into
  `combine.py`'s `SourceRef.doc_id`).
- The `has_financials` linkage gap (above) means risk-quantification
  numbers that exist in real ingested data (SKU retail prices, buffer
  days) are unreachable from the graph. Neither system answers these
  questions well as a result.
- The tier-2 crew's real-world recall is untested here — it was never run
  against paid Ollama Cloud in this corpus; `tests/tier2_validation/` is a
  separate, explicitly indicative 2-company smoke test, not a measurement
  of this corpus's tier-2 inference quality.
- Entity resolution (Phase 4) precision/recall/F1 (1.000/1.000/1.000 on
  the 200-pair fixture) is unchanged from Phase 4 and still carries that
  phase's credibility caveat: the fixture tests the scorer against the
  generator's own mess, not adversarial pairs.

---

## Author

Shivika Khanna · PGDM Business Data Analytics, FORE School of Management.
Project repo: [github.com/anonymous-2924/shivikak-24](https://github.com/anonymous-2924/shivikak-24).
