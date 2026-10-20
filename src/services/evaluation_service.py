"""Evaluation service: runs a benchmark of questions and computes retrieval
metrics (Hit@k, MRR) plus abstention correctness.

Scores are computed from real retrieval runs against the current index — never
fabricated. A benchmark with no indexed data yields explicit zero/NA results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.rag.retrieval import RetrievalFilter
from src.services.context import AppContext


@dataclass
class BenchmarkItem:
    question: str
    # a relevant chunk is one whose document_id is in relevant_document_ids
    relevant_document_ids: list[str] = field(default_factory=list)
    expect_abstention: bool = False
    companies: Optional[list[str]] = None


@dataclass
class EvalResult:
    n: int
    hit_at_k: float
    mrr: float
    abstention_correct: float
    k: int
    config: dict
    per_item: list[dict] = field(default_factory=list)
    timestamp: str = ""


class EvaluationService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    def run(self, items: list[BenchmarkItem], *, k: int = 8, hybrid: bool = True) -> EvalResult:
        hits, rr, abst_ok = 0, 0.0, 0
        per_item = []
        for it in items:
            flt = RetrievalFilter(company_names=it.companies) if it.companies else None
            chunks = self.ctx.index.retrieve(it.question, top_k=k, flt=flt, hybrid=hybrid)
            retrieved_docs = [c.metadata.get("document_id") for c in chunks]

            if it.expect_abstention:
                correct = len(chunks) == 0
                abst_ok += 1 if correct else 0
                per_item.append({"question": it.question, "expect_abstention": True,
                                 "abstained": len(chunks) == 0, "correct": correct})
                continue

            rank = None
            for idx, did in enumerate(retrieved_docs, start=1):
                if did in it.relevant_document_ids:
                    rank = idx
                    break
            if rank:
                hits += 1
                rr += 1.0 / rank
            per_item.append({"question": it.question, "hit": rank is not None,
                             "rank": rank, "retrieved": retrieved_docs[:k]})

        scored = [i for i in items if not i.expect_abstention]
        abst_items = [i for i in items if i.expect_abstention]
        n_scored = len(scored) or 1
        result = EvalResult(
            n=len(items),
            hit_at_k=round(hits / n_scored, 3) if scored else 0.0,
            mrr=round(rr / n_scored, 3) if scored else 0.0,
            abstention_correct=round(abst_ok / (len(abst_items) or 1), 3) if abst_items else 0.0,
            k=k,
            config={"hybrid": hybrid, "embedder": self.ctx.embedder.name,
                    "rerank": self.ctx.rerank_status.enabled},
            per_item=per_item,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._persist(result)
        return result

    def _persist(self, result: EvalResult) -> None:
        out_dir = self.ctx.settings.paths()["evaluations"]
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = result.timestamp.replace(":", "").replace("-", "")[:15]
        (out_dir / f"eval_{stamp}.json").write_text(
            json.dumps(result.__dict__, indent=2, default=str), encoding="utf-8"
        )

    @staticmethod
    def load_benchmark(path: str) -> list[BenchmarkItem]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return [BenchmarkItem(**d) for d in data]
