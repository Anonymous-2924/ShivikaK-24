"""Run the RAG evaluation benchmark against the current index.

Run:  python scripts/evaluate_rag.py data/evaluations/benchmark.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.context import build_context
from src.services.evaluation_service import EvaluationService


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/evaluate_rag.py <benchmark.json>")
        return 1
    ctx = build_context()
    ev = EvaluationService(ctx)
    items = ev.load_benchmark(sys.argv[1])
    for hybrid in (False, True):
        res = ev.run(items, k=ctx.settings.top_k, hybrid=hybrid)
        label = "hybrid" if hybrid else "dense-only"
        print(f"[{label}] Hit@{res.k}={res.hit_at_k} MRR={res.mrr} "
              f"abstention_correct={res.abstention_correct} (n={res.n})")
    print("Saved per-run JSON under data/evaluations/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
