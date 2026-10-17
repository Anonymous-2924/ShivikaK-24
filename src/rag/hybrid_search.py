"""Hybrid retrieval: BM25 keyword search + dense vector search, fused with RRF.

This is a *real* hybrid implementation — BM25 uses ``rank_bm25`` when available
(with a dependency-free fallback), and results are combined with Reciprocal
Rank Fusion. Plain vector search is never mislabelled as hybrid.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional, Sequence

try:
    from rank_bm25 import BM25Okapi

    _HAS_BM25 = True
except Exception:  # pragma: no cover
    _HAS_BM25 = False


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class ScoredDoc:
    doc_id: str
    score: float
    text: str = ""


class BM25Index:
    """Keyword index. Uses rank_bm25 when present; else a TF-IDF-ish fallback."""

    def __init__(self, doc_ids: Sequence[str], texts: Sequence[str]):
        self.doc_ids = list(doc_ids)
        self._tokens = [tokenize(t) for t in texts]
        self._texts = list(texts)
        if _HAS_BM25 and self._tokens:
            self._bm25 = BM25Okapi(self._tokens)
        else:
            self._bm25 = None
            self._df = self._document_frequencies()

    def _document_frequencies(self) -> dict[str, int]:
        df: dict[str, int] = {}
        for toks in self._tokens:
            for term in set(toks):
                df[term] = df.get(term, 0) + 1
        return df

    def search(self, query: str, top_k: int = 10) -> list[ScoredDoc]:
        q = tokenize(query)
        if not q or not self.doc_ids:
            return []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(q)
        else:
            scores = self._fallback_scores(q)
        ranked = sorted(zip(self.doc_ids, scores, self._texts), key=lambda x: x[1], reverse=True)
        return [ScoredDoc(d, float(s), t) for d, s, t in ranked[:top_k] if s > 0]

    def _fallback_scores(self, q: list[str]) -> list[float]:
        n = len(self._tokens)
        scores = []
        for toks in self._tokens:
            tf: dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for term in q:
                if term in tf:
                    idf = math.log(1 + n / (1 + self._df.get(term, 0)))
                    s += (tf[term] / (len(toks) or 1)) * idf
            scores.append(s)
        return scores


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[ScoredDoc]], *, k: int = 60, top_k: int = 10
) -> list[ScoredDoc]:
    """Fuse ranked lists with RRF: score = sum(1 / (k + rank)).

    RRF is robust because it ignores the raw score scales of the different
    retrievers and uses only rank position.
    """
    fused: dict[str, float] = {}
    texts: dict[str, str] = {}
    for results in result_lists:
        for rank, doc in enumerate(results, start=1):
            fused[doc.doc_id] = fused.get(doc.doc_id, 0.0) + 1.0 / (k + rank)
            if doc.text and doc.doc_id not in texts:
                texts[doc.doc_id] = doc.text
    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return [ScoredDoc(d, s, texts.get(d, "")) for d, s in ranked[:top_k]]


def bm25_available() -> bool:
    return _HAS_BM25
