# FinSight AI — Architecture

FinSight AI analyses annual reports of Indian listed companies and answers
financial research questions with **source-grounded** evidence. It separates:

1. **Facts reported** in documents (with citations),
2. **Metrics calculated** deterministically from reported figures,
3. **AI interpretation**, and
4. **Missing / conflicting / unverified** information (flagged, never guessed).

## Layers

```
Streamlit UI (app.py + pages/1..7)
        │
   Services (composition root + use-cases)
   context · document · company · research · evaluation
        │
 ┌──────┴───────────────────────────────────────────────┐
 │                         │                              │
RAG layer            Finance engine               Agents (CrewAI)
chunking             metrics (deterministic)       planner→researcher→
embeddings           financial_data               analyst→reviewer
indexing (Qdrant)    comparisons                   tools: retrieval + calc
hybrid (BM25+RRF)    risk_flags                    (deterministic fallback
retrieval/citations                                 orchestrator if no crewai)
query_engine
        │
   Ingestion                         Storage
   parser (pdfplumber/Docling)       Qdrant (vectors)
   parse_validation                  SQLite metadata + chunks
   file_validation (hash/SSRF)       query cache
   table_extraction                  parsed artifacts (md + json)
   source adapters (manual)
```

## Key design rules

- **One RAG implementation.** CrewAI orchestrates; LlamaIndex/Qdrant own
  retrieval. Agents call the same retrieval + calculation tools — no second
  RAG.
- **LLM never does arithmetic.** `src/finance/metrics.py` is the sole
  authoritative calculator, with provenance on every input.
- **Provenance everywhere.** `ChunkMetadata` carries company, FY, basis,
  section, physical PDF page vs printed page label, source URL/filename.
- **Graceful degradation.** Missing heavy deps (Docling, sentence-transformers,
  CrewAI) or an absent LLM key never break the app; features downgrade and say
  so (evidence-only answers, hashing embedder, fallback orchestrator).
- **Anti-hallucination.** `src/rag/citations.py` verifies quotes/numbers against
  retrieved evidence; the query engine abstains when evidence is insufficient.

## Data flow (ingestion)

file → validate (hash, size, type, safe name) → parse → parse-quality checks →
export markdown+json → structure-aware chunk → embed (batched) → upsert to
Qdrant + chunk repo → record document/chunk metadata.

## Data flow (query)

question → normalize + extract FY → metadata filter → dense (Qdrant) + BM25 →
RRF fusion → optional rerank → citations → (optional) grounded LLM synthesis →
grounding verification → answer or abstention.
