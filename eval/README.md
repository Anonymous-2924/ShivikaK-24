# eval/

Phase 6. 45 hand-written questions (`questions.jsonl`) with ground truth
computed from the actual generated corpus (not guessed), spanning:
exposure tracing (12), risk quantification (11), tier-2 inference (11),
monitoring (11).

Benchmarks GraphRAG (`src/retrieve/service.py`) against a plain
vector-RAG baseline (`baseline_vector_rag.py`: embed -> top-k Qdrant ->
concatenate chunks -> one LLM call, no graph, no DuckDB, no router) on:

- retrieval precision
- path correctness (Jaccard of returned vs. expected SKU ids)
- hallucination rate (entity-id-shaped mentions not in the real graph)
- latency (p50, p95)
- cost per query (USD — $0 for this project's actual free-tier models;
  see `metrics.py:MODEL_RATES_USD_PER_1K_TOKENS`)

```
python -m eval.run [--systems graphrag,baseline] [--limit N]
```

prints a comparison table and writes `results.md` + `results_detail.jsonl`.

**Credibility note.** Results include failure cases and, where relevant,
state plainly that a category couldn't be measured in the environment
the run happened in (rather than fabricating a number). See the README's
"Reported measurements" section for what this project's own runs found.
