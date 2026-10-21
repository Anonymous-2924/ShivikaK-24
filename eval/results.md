# Phase 6 eval results

Questions: 45. Systems: graphrag, baseline.

## Infrastructure actually reachable during this run

- Neo4j: reachable
- Qdrant/embeddings: reachable
- Ollama Cloud (baseline answer LLM): reachable

## Overall (all categories)

| System | Mean retrieval precision | Mean path correctness (n scored) | Mean hallucination rate (n scored) | p50 latency (ms) | p95 latency (ms) | Total cost (USD) | Errors |
|---|---|---|---|---|---|---|---|
| graphrag | 0.249 | 0.381 (23) | 0.000 (10) | 163.6 | 1670.0 | 0.0000 | 0/45 |
| baseline | 0.050 | 0.087 (23) | n/a (0 scored) | 4301.5 | 11754.6 | 0.0000 | 0/45 |

## By category

### exposure_tracing

| System | Mean retrieval precision | Mean path correctness (n) | Mean hallucination rate (n) | Errors |
|---|---|---|---|---|
| graphrag | 0.833 | 0.653 (12) | n/a (0 scored) | 0/12 |
| baseline | 0.000 | 0.167 (12) | n/a (0 scored) | 0/12 |

### monitoring

| System | Mean retrieval precision | Mean path correctness (n) | Mean hallucination rate (n) | Errors |
|---|---|---|---|---|
| graphrag | 0.000 | n/a (0 scored) | 0.000 (10) | 0/11 |
| baseline | 0.177 | n/a (0 scored) | n/a (0 scored) | 0/11 |

### risk_quantification

| System | Mean retrieval precision | Mean path correctness (n) | Mean hallucination rate (n) | Errors |
|---|---|---|---|---|
| graphrag | 0.111 | 0.084 (11) | n/a (0 scored) | 0/11 |
| baseline | 0.000 | 0.000 (11) | n/a (0 scored) | 0/11 |

### tier2_inference

| System | Mean retrieval precision | Mean path correctness (n) | Mean hallucination rate (n) | Errors |
|---|---|---|---|---|
| graphrag | 0.000 | n/a (0 scored) | n/a (0 scored) | 0/11 |
| baseline | 0.027 | n/a (0 scored) | n/a (0 scored) | 0/11 |

## Failures (every error, not summarised away)

No hard errors — every question returned a result object (possibly 'no evidence found'), nothing raised.
