"""Qdrant client wrapper.

One collection (``blastradius_narrative``) holds both narrative chunks and
data cards. The payload's ``kind`` discriminates them so the retrieval
router (Phase 5) can filter.
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

COLLECTION = "blastradius_narrative"


@dataclass(frozen=True)
class IndexDoc:
    """One thing to embed and store."""
    doc_id: str                 # stable id for this piece of content
    text: str                   # what gets embedded
    kind: str                   # "chunk" | "data_card"
    source_file: str
    chunk_index: int | None     # None for data_card
    confidence: float
    extraction_method: str      # structured | llm_extracted | inferred | manual
    extra_payload: dict         # anything else callers want persisted


class QdrantIndex:
    def __init__(self, *, url: str, vector_dim: int,
                 api_key: str | None = None,
                 collection: str = COLLECTION) -> None:
        from qdrant_client import QdrantClient
        self.collection = collection
        self.vector_dim = vector_dim
        self.client = QdrantClient(url=url, api_key=api_key)

    def ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection in existing:
            info = self.client.get_collection(self.collection)
            # Both the single-vector and named-vector shapes carry .size.
            cfg = info.config.params.vectors
            dim = getattr(cfg, "size", None)
            if dim is not None and dim != self.vector_dim:
                raise RuntimeError(
                    f"collection {self.collection!r} exists with vector dim "
                    f"{dim}, but config says {self.vector_dim}. Drop the "
                    f"collection or change OLLAMA_EMBED_DIM to match."
                )
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.vector_dim,
                                         distance=Distance.COSINE),
        )

    def upsert(self, docs: Sequence[IndexDoc],
               vectors: Sequence[Sequence[float]]) -> None:
        from qdrant_client.models import PointStruct
        points: list[PointStruct] = []
        for doc, vec in zip(docs, vectors, strict=True):
            payload = {
                "doc_id": doc.doc_id,
                "kind": doc.kind,
                "source_file": doc.source_file,
                "chunk_index": doc.chunk_index,
                "confidence": doc.confidence,
                "extraction_method": doc.extraction_method,
                "text": doc.text[:2000],   # bounded; full text is on disk
                **doc.extra_payload,
            }
            points.append(PointStruct(
                id=_point_id(doc.doc_id),
                vector=list(vec), payload=payload,
            ))
        self.client.upsert(collection_name=self.collection, points=points)

    def count(self) -> int:
        return int(self.client.count(collection_name=self.collection,
                                      exact=True).count)

    def search(self, vector: Sequence[float], *, top_k: int = 20,
               kind: str | None = None) -> list[dict]:
        """kNN search. Optionally filter payload ``kind`` ("chunk" |
        "data_card"). Returns payload dicts with a ``score`` key added."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        query_filter = None
        if kind is not None:
            query_filter = Filter(must=[
                FieldCondition(key="kind", match=MatchValue(value=kind)),
            ])
        hits = self.client.query_points(
            collection_name=self.collection, query=list(vector),
            limit=top_k, query_filter=query_filter,
        ).points
        return [{**h.payload, "score": h.score} for h in hits]


def _point_id(doc_id: str) -> str:
    """Deterministic UUID derived from doc_id — makes upsert idempotent."""
    digest = hashlib.sha1(doc_id.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16]))
