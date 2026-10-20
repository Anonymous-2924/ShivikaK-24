"""Qdrant vector store wrapper (default vector DB).

Supports embedded on-disk mode (no server, no Docker) and server mode. Provides
upsert with metadata payloads, metadata-filtered search, idempotent deletes by
document, and a health check. Persistence across restarts is via the on-disk
path or the remote server.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.rag.retrieval import RetrievalFilter
from src.utils.errors import StorageError
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class VectorHit:
    chunk_id: str
    score: float
    text: str
    metadata: dict


class QdrantStore:
    def __init__(self, *, mode: str, path: Optional[str], url: Optional[str],
                 api_key: Optional[str], collection: str, dim: int):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qmodels
        except Exception as exc:  # pragma: no cover
            raise StorageError(f"qdrant-client not installed: {exc}") from exc
        self._qmodels = qmodels
        self.collection = collection
        self.dim = dim
        if mode == "server":
            if not url:
                raise StorageError("qdrant_url required for server mode.")
            self._client = QdrantClient(url=url, api_key=api_key)
        else:
            self._client = QdrantClient(path=path)  # embedded, on-disk
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        qm = self._qmodels
        existing = {c.name for c in self._client.get_collections().collections}
        if self.collection not in existing:
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=self.dim, distance=qm.Distance.COSINE),
            )

    def upsert(self, *, ids: Sequence[str], vectors: Sequence[Sequence[float]],
               payloads: Sequence[dict]) -> None:
        qm = self._qmodels
        points = [
            qm.PointStruct(id=_point_id(cid), vector=list(vec),
                           payload={**pl, "chunk_id": cid})
            for cid, vec, pl in zip(ids, vectors, payloads)
        ]
        self._client.upsert(collection_name=self.collection, points=points)

    def search(self, vector: Sequence[float], *, top_k: int = 8,
               flt: Optional[RetrievalFilter] = None) -> list[VectorHit]:
        qfilter = self._to_qdrant_filter(flt) if flt else None
        response = self._client.query_points(
            collection_name=self.collection, query=list(vector),
            limit=top_k, query_filter=qfilter, with_payload=True,
        )
        hits = []
        for r in response.points:
            payload = r.payload or {}
            hits.append(VectorHit(
                chunk_id=payload.get("chunk_id", str(r.id)),
                score=float(r.score), text=payload.get("text", ""), metadata=payload,
            ))
        return hits

    def delete_document(self, document_id: str) -> None:
        qm = self._qmodels
        self._client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(filter=qm.Filter(must=[
                qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))
            ])),
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def count(self) -> int:
        try:
            return self._client.count(self.collection, exact=True).count
        except Exception:
            return 0

    def health(self) -> dict:
        try:
            return {"ok": True, "collection": self.collection, "points": self.count()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _to_qdrant_filter(self, flt: RetrievalFilter):
        qm = self._qmodels
        must = []

        def add_any(key, values):
            if values:
                must.append(qm.FieldCondition(key=key, match=qm.MatchAny(any=list(values))))

        add_any("company_id", flt.company_ids)
        add_any("company_name", flt.company_names)
        add_any("financial_year", flt.financial_years)
        add_any("report_type", flt.report_types)
        add_any("content_type", flt.content_types)
        if flt.basis:
            must.append(qm.FieldCondition(key="basis", match=qm.MatchValue(value=flt.basis)))
        return qm.Filter(must=must) if must else None


def _point_id(chunk_id: str) -> int:
    import hashlib

    return int(hashlib.sha1(chunk_id.encode()).hexdigest()[:15], 16)
