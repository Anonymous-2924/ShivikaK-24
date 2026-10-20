# eval/

Phase 6 target. 40–60 hand-written questions with ground-truth answers
spanning: exposure tracing, risk quantification, tier-2 inference,
monitoring.

Benchmarks GraphRAG against a plain vector-RAG baseline on:

- retrieval precision
- path correctness
- hallucination rate
- latency (p50, p95)
- cost per query (USD)

`python -m eval.run` prints a comparison table and writes `eval/results.md`.

**Credibility note.** Results will include failure cases. Measured numbers
are the point; a glossy "it works" report is not.
