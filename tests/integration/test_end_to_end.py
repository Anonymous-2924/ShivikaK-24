"""End-to-end pipeline test using the hashing embedder and embedded Qdrant.

No external services required. Exercises: parse -> chunk -> index -> hybrid
retrieve -> citations -> abstention, and persistence across a store restart.
"""
import os

import pytest

from src.config.settings import Settings
from src.ingestion.metadata import DocumentMetadata
from src.rag.embeddings import HashingEmbedder
from src.rag.indexing import RagIndex
from src.rag.ingestion_pipeline import ingest_document
from src.rag.query_engine import QueryEngine
from src.rag.retrieval import RetrievalFilter
from src.storage.qdrant_store import QdrantStore
from src.storage.repositories import ChunkRepository

SAMPLE_TEXT = """## Management Discussion and Analysis

Revenue from operations grew to 15000 crore in FY2023-24 from 12000 crore in
FY2022-23, driven by volume growth in the digital services segment. Operating
margin declined to 22 percent from 24 percent due to higher employee costs and
pricing pressure in the financial services vertical.

## Notes to Accounts

The company disclosed contingent liabilities of 450 crore and several related
party transactions with its subsidiaries during the year.
"""


def _make_index(tmp_path):
    store = QdrantStore(mode="local", path=str(tmp_path / "qdrant"), url=None, api_key=None,
                        collection="test_reports", dim=384)
    chunks = ChunkRepository(str(tmp_path / "chunks.db"))
    return RagIndex(store, chunks, HashingEmbedder(384)), store, chunks


def _ingest_sample(tmp_path, index):
    src_file = tmp_path / "sample.md"
    src_file.write_text(SAMPLE_TEXT, encoding="utf-8")
    doc = DocumentMetadata(
        document_id="docA", company_name="Example Ltd", financial_year="FY2023-24",
        report_type="Annual Report", source_filename="sample.md", local_path=str(src_file),
        file_size_bytes=len(SAMPLE_TEXT),
    )
    res = ingest_document(doc, index, parsed_dir=str(tmp_path / "parsed"))
    return doc, res


def test_ingest_and_retrieve(tmp_path):
    index, _, _ = _make_index(tmp_path)
    doc, res = _ingest_sample(tmp_path, index)
    assert res.ok and res.chunks_indexed > 0

    engine = QueryEngine(index)  # no LLM -> evidence-only mode
    ans = engine.answer("Why did operating margin decline?", top_k=4, use_llm=False)
    assert not ans.abstained
    assert ans.citations
    assert "Example Ltd" in ans.citations[0].render()
    # retrieval surfaced the margin discussion
    assert any("margin" in c.text.lower() for c in ans.evidence)


def test_metadata_filter_narrows(tmp_path):
    index, _, _ = _make_index(tmp_path)
    _ingest_sample(tmp_path, index)
    engine = QueryEngine(index)
    flt = RetrievalFilter(company_names=["No Such Co"])
    ans = engine.answer("revenue", top_k=4, flt=flt, use_llm=False)
    assert ans.abstained  # nothing matches the filter


def test_persistence_across_restart(tmp_path):
    index, store, chunks = _make_index(tmp_path)
    _ingest_sample(tmp_path, index)
    n_before = store.count()
    assert n_before > 0
    del index, store, chunks  # simulate shutdown

    # Reopen from the same on-disk paths.
    store2 = QdrantStore(mode="local", path=str(tmp_path / "qdrant"), url=None, api_key=None,
                         collection="test_reports", dim=384)
    chunks2 = ChunkRepository(str(tmp_path / "chunks.db"))
    index2 = RagIndex(store2, chunks2, HashingEmbedder(384))
    assert store2.count() == n_before
    ans = QueryEngine(index2).answer("contingent liabilities", top_k=3, use_llm=False)
    assert not ans.abstained


def test_idempotent_reindex_no_duplicates(tmp_path):
    index, store, _ = _make_index(tmp_path)
    doc, _ = _ingest_sample(tmp_path, index)
    n1 = store.count()
    ingest_document(doc, index, parsed_dir=str(tmp_path / "parsed"))  # re-ingest same doc
    assert store.count() == n1  # chunk ids are stable -> upsert, not duplicate


def test_delete_removes_vectors(tmp_path):
    index, store, _ = _make_index(tmp_path)
    doc, _ = _ingest_sample(tmp_path, index)
    assert store.count() > 0
    index.delete_document(doc.document_id)
    assert store.count() == 0
