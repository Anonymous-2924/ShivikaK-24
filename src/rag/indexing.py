"""Index orchestration: embeddings + Qdrant vectors + chunk repository.

Provides idempotent indexing (re-indexing an unchanged document does not create
duplicate chunks), deletion, and hybrid retrieval (dense + BM25 fused via RRF).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.rag.embeddings import EmbeddingProvider
from src.rag.hybrid_search import BM25Index, ScoredDoc, reciprocal_rank_fusion
from src.rag.retrieval import RetrievalFilter
from src.storage.qdrant_store import QdrantStore, VectorHit
from src.storage.repositories import ChunkRepository
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict
    score: float


class RagIndex:
    def __init__(self, store: QdrantStore, chunks: ChunkRepository, embedder: EmbeddingProvider):
        self.store = store
        self.chunks = chunks
        self.embedder = embedder

    def index_chunks(self, records: list[dict], *, batch_size: int = 32) -> int:
        """Index chunk records.

        Each record: {chunk_id, document_id, text, metadata(dict)}. Idempotent
        on chunk_id. Returns the number of chunks indexed.
        """
        if not records:
            return 0
        texts = [r["text"] for r in records]
        vectors = self.embedder.embed_batched(texts, batch_size=batch_size)
        ids = [r["chunk_id"] for r in records]
        payloads = [{**r["metadata"], "text": r["text"], "document_id": r["document_id"]}
                    for r in records]
        self.store.upsert(ids=ids, vectors=vectors, payloads=payloads)
        self.chunks.upsert_many(
            [(r["chunk_id"], r["document_id"], r["text"], r["metadata"]) for r in records]
        )
        log.info("Indexed %d chunks.", len(records))
        return len(records)

    def delete_document(self, document_id: str) -> None:
        self.store.delete_document(document_id)
        self.chunks.delete_document(document_id)

    def retrieve(self, query: str, *, top_k: int = 8, flt: Optional[RetrievalFilter] = None,
                 hybrid: bool = True) -> list[RetrievedChunk]:
        qvec = self.embedder.embed([query])[0]
        dense_hits: list[VectorHit] = self.store.search(qvec, top_k=top_k * 2, flt=flt)
        dense = [ScoredDoc(h.chunk_id, h.score, h.text) for h in dense_hits]
        meta_by_id = {h.chunk_id: h.metadata for h in dense_hits}

        if not hybrid:
            return self._to_chunks(dense[:top_k], meta_by_id)

        # BM25 over the filtered corpus (respects the same metadata filter).
        corpus = self.chunks.all_chunks()
        if flt:
            corpus = [(cid, txt, meta) for cid, txt, meta in corpus if flt.matches(meta)]
        if corpus:
            bm = BM25Index([c[0] for c in corpus], [c[1] for c in corpus])
            kw = bm.search(query, top_k=top_k * 2)
            for cid, txt, meta in corpus:
                meta_by_id.setdefault(cid, meta)
            kw_texts = {c[0]: c[1] for c in corpus}
            for sd in kw:
                sd.text = kw_texts.get(sd.doc_id, sd.text)
        else:
            kw = []

        fused = reciprocal_rank_fusion([dense, kw], top_k=top_k)
        return self._to_chunks(fused, meta_by_id)

    def _to_chunks(self, scored: list[ScoredDoc], meta_by_id: dict) -> list[RetrievedChunk]:
        out = []
        need = [s.doc_id for s in scored if not s.text or s.doc_id not in meta_by_id]
        fetched = self.chunks.get_texts(need) if need else {}
        for s in scored:
            text = s.text
            meta = meta_by_id.get(s.doc_id, {})
            if (not text or not meta) and s.doc_id in fetched:
                ftext, fmeta = fetched[s.doc_id]
                text = text or ftext
                meta = meta or fmeta
            out.append(RetrievedChunk(s.doc_id, text, meta, s.score))
        return out
