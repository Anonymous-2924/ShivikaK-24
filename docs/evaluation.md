# Evaluation

The evaluation suite (`src/services/evaluation_service.py`, run via
`scripts/evaluate_rag.py`) scores retrieval against a manually-authored
benchmark of financial questions, including questions whose answer is absent
(should abstain). All numbers are computed from real retrieval runs — none are
fabricated.

## Metrics implemented
- **Hit@k** — a relevant document appears in the top-k.
- **MRR** — mean reciprocal rank of the first relevant document.
- **Abstention correctness** — for questions with no supporting document, the
  system returns no evidence (abstains).

Citation precision/coverage, numerical-accuracy and parsing-accuracy checks are
supported conceptually by the grounding tools (`src/rag/citations.py`,
`tests/`); a larger labelled corpus is needed to report them meaningfully.

## Benchmark
`data/evaluations/benchmark.json` is a template. After ingesting real reports,
replace `REPLACE_WITH_DOC_ID` with the actual `document_id`s (shown in Document
Management / returned by the ingest script), then:
```
python scripts/evaluate_rag.py data/evaluations/benchmark.json
```
Per-run results are saved to `data/evaluations/eval_*.json` with the dataset,
config (embedder, hybrid on/off, rerank), and timestamp.

## Demonstration run (honest, small-scale)
A 4-item synthetic benchmark over a single synthetic report, using the
**hashing fallback embedder** (no model download), on 2026-10-17:

| Config | Hit@5 | MRR | n |
|---|---|---|---|
| dense-only | 0.75 | 0.75 | 4 |
| hybrid (BM25+RRF) | 0.75 | 0.75 | 4 |

**Caveats (important):** this is a tiny synthetic corpus with the weak hashing
embedder, so these numbers demonstrate the harness works — they are **not** a
quality claim. Hybrid and dense tie here because a single-document corpus
produces the same ranking; a difference is expected only on a larger,
multi-document corpus with a real semantic embedder
(`EMBEDDING_PROVIDER=local`). Reproduce with the snippet in the project README
or by ingesting real reports and running the script above.
