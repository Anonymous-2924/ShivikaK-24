"""Semantic dispatch: embed the question, kNN against Qdrant.

Reuses Phase 3's ``Embedder`` and ``QdrantIndex`` as-is — this module adds
no new embedding or indexing logic, only the query-side call.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TOP_K = 20


@dataclass
class SemanticHit:
    doc_id: str
    kind: str              # "chunk" | "data_card"
    text: str
    source_file: str
    score: float
    confidence: float
    extraction_method: str


def semantic_search(question: str, *, embedder, index, top_k: int = DEFAULT_TOP_K,
                     kind: str | None = "chunk") -> list[SemanticHit]:
    """``embedder`` needs ``.embed_one(text) -> list[float]``; ``index``
    needs ``.search(vector, top_k=..., kind=...) -> list[dict]`` — i.e.
    ``src.index.embeddings.Embedder`` and ``src.index.qdrant.QdrantIndex``,
    or test doubles with the same shape."""
    vector = embedder.embed_one(question)
    raw = index.search(vector, top_k=top_k, kind=kind)
    return [
        SemanticHit(
            doc_id=r["doc_id"], kind=r["kind"], text=r.get("text", ""),
            source_file=r.get("source_file", ""), score=float(r["score"]),
            confidence=float(r.get("confidence", 0.0)),
            extraction_method=r.get("extraction_method", "unknown"),
        )
        for r in raw
    ]
