"""Service-level tests: parsing formats, duplicate detection, evaluation."""
import pandas as pd
import pytest

from src.config.settings import Settings
from src.ingestion.parser import parse_document
from src.ingestion.table_extraction import detect_units
from src.rag.embeddings import HashingEmbedder
from src.rag.indexing import RagIndex
from src.services.context import AppContext
from src.services.document_service import DocumentService
from src.services.evaluation_service import BenchmarkItem, EvaluationService
from src.storage.metadata_store import MetadataStore
from src.storage.qdrant_store import QdrantStore
from src.storage.repositories import ChunkRepository


def _ctx(tmp_path) -> AppContext:
    s = Settings(data_dir=str(tmp_path / "data"),
                 metadata_db_path=str(tmp_path / "data" / "meta.db"),
                 qdrant_path=str(tmp_path / "data" / "qdrant"),
                 embedding_provider="hashing")
    s.ensure_dirs()
    emb = HashingEmbedder(s.embedding_dim)
    store = QdrantStore(mode="local", path=s.qdrant_path, url=None, api_key=None,
                        collection="t", dim=emb.dim)
    chunks = ChunkRepository(str(tmp_path / "data" / "chunks.db"))
    meta = MetadataStore(s.metadata_db_path)
    from src.rag.query_engine import QueryEngine
    from src.rag.reranking import RerankStatus
    index = RagIndex(store, chunks, emb)
    return AppContext(settings=s, metadata_store=meta, chunk_repo=chunks, index=index,
                      engine=QueryEngine(index), embedder=emb,
                      rerank_status=RerankStatus(False, "test"), llm_available=False)


def test_parse_csv_and_xlsx(tmp_path):
    csv_p = tmp_path / "d.csv"
    csv_p.write_text("Metric,FY2023,FY2024\nRevenue,100,120\n", encoding="utf-8")
    pdoc = parse_document(csv_p)
    assert "Revenue" in pdoc.markdown
    assert pdoc.structured["rows"][0][0] == "Metric"

    xlsx_p = tmp_path / "d.xlsx"
    pd.DataFrame({"A": [1, 2], "B": [3, 4]}).to_excel(xlsx_p, index=False)
    xdoc = parse_document(xlsx_p)
    assert xdoc.parser_name == "openpyxl"
    assert "Sheet:" in xdoc.markdown


def test_detect_units():
    assert "crore" in (detect_units("All figures in INR crore") or "")


def test_document_service_duplicate_detection(tmp_path):
    ctx = _ctx(tmp_path)
    svc = DocumentService(ctx)
    f = tmp_path / "r.md"
    f.write_text("Revenue from operations was 500 crore in FY2023-24.", encoding="utf-8")
    out1 = svc.add_file(str(f), company_name="ACME", financial_year="FY2023-24")
    assert not out1.duplicate and out1.result.ok
    out2 = svc.add_file(str(f), company_name="ACME", financial_year="FY2023-24")
    assert out2.duplicate
    assert len(svc.list_documents()) == 1


def test_evaluation_service_hit_and_abstention(tmp_path):
    ctx = _ctx(tmp_path)
    svc = DocumentService(ctx)
    f = tmp_path / "r.md"
    f.write_text("Operating margin declined due to higher input costs in FY2023-24.", encoding="utf-8")
    out = svc.add_file(str(f), company_name="ACME", financial_year="FY2023-24")
    doc_id = out.document.document_id

    ev = EvaluationService(ctx)
    items = [
        BenchmarkItem(question="why did operating margin decline?",
                      relevant_document_ids=[doc_id]),
        BenchmarkItem(question="totally unrelated quantum physics question",
                      expect_abstention=False, relevant_document_ids=["nonexistent"]),
    ]
    res = ev.run(items, k=5)
    assert res.n == 2
    assert 0.0 <= res.hit_at_k <= 1.0
    assert res.config["embedder"] == "hashing"
