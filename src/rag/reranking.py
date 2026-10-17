"""Optional cross-encoder reranking.

Disabled by default. When a compatible cross-encoder (sentence-transformers) is
installed and enabled, it reorders candidates by relevance. When unavailable,
retrieval still works and the caller is told reranking is OFF — never silently
pretended.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RerankStatus:
    enabled: bool
    reason: str = ""


class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        from sentence_transformers import CrossEncoder  # raises if missing

        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, chunks: list, top_k: int | None = None) -> list:
        pairs = [(query, c.text) for c in chunks]
        scores = self._model.predict(pairs)
        ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
        out = [c for c, _ in ranked]
        return out[:top_k] if top_k else out


def build_reranker(settings) -> tuple[Reranker | None, RerankStatus]:
    if not settings.rerank_enabled:
        return None, RerankStatus(False, "Reranking disabled in settings.")
    try:
        return Reranker(), RerankStatus(True, "Cross-encoder reranker active.")
    except Exception as exc:
        return None, RerankStatus(False, f"Reranker unavailable: {exc}")
