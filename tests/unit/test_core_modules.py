"""Tests for validation, chunking, citations, retrieval, risk, comparisons, store."""
import os
import tempfile

import pytest

from src.ingestion.file_validation import (
    safe_filename, resolve_within, is_duplicate, normalize_source_url, validate_file,
)
from src.ingestion.metadata import DocumentMetadata, make_document_id, sha256_of_bytes
from src.rag.chunking import chunk_narrative, chunk_table, chunk_document, CONTENT_TABLE, CONTENT_MDNA
from src.rag.citations import (
    Citation, passage_is_grounded, numbers_supported, extract_numbers,
)
from src.rag.retrieval import RetrievalFilter, extract_financial_years, dedupe_preserving_order
from src.rag.hybrid_search import BM25Index, reciprocal_rank_fusion, ScoredDoc
from src.finance.risk_flags import scan_text
from src.finance.financial_data import FinancialFact, FinancialFactSet
from src.finance.comparisons import build_trend, compare_peers
from src.storage.metadata_store import MetadataStore
from src.utils.errors import ValidationError


# ---- file validation ----------------------------------------------------
def test_safe_filename_strips_traversal():
    assert "/" not in safe_filename("../../etc/passwd")
    assert ".." not in safe_filename("..\\..\\win.ini")
    assert safe_filename("") == "file"


def test_resolve_within_blocks_escape(tmp_path):
    # Traversal is neutralised by safe_filename, so the path is forced inside.
    escaped = resolve_within(tmp_path, "../../outside.txt")
    assert str(escaped).startswith(str(tmp_path.resolve()))
    assert ".." not in str(escaped)
    inside = resolve_within(tmp_path, "report.pdf")
    assert str(inside).startswith(str(tmp_path.resolve()))


def test_duplicate_detection_and_url_norm():
    assert is_duplicate("abc", {"abc", "def"})
    assert not is_duplicate("xyz", {"abc"})
    assert normalize_source_url("HTTPS://Example.com/a/") == "https://example.com/a"


def test_validate_file_rejects_unsupported(tmp_path):
    p = tmp_path / "bad.exe"
    p.write_bytes(b"x")
    with pytest.raises(ValidationError):
        validate_file(p)


def test_validate_file_accepts_pdf(tmp_path):
    p = tmp_path / "ok.pdf"
    p.write_bytes(b"%PDF-1.4 content")
    info = validate_file(p)
    assert info.extension == ".pdf"
    assert len(info.sha256) == 64


# ---- metadata ------------------------------------------------------------
def test_document_id_stable():
    h = sha256_of_bytes(b"data")
    a = make_document_id("Infosys", "FY2023-24", h)
    b = make_document_id("Infosys", "FY2023-24", h)
    assert a == b


def test_citation_label():
    d = DocumentMetadata(document_id="d", company_name="Infosys", financial_year="FY2023-24",
                         report_type="Annual Report", source_filename="x.pdf")
    assert "Infosys" in d.citation_label()


# ---- chunking ------------------------------------------------------------
def test_chunk_narrative_overlap_and_coverage():
    text = " ".join(f"Sentence number {i} about revenue." for i in range(40))
    chunks = chunk_narrative(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)


def test_chunk_table_is_single_chunk_and_typed():
    chunks = chunk_table("| A | B |\n|---|---|\n| 1 | 2 |", section_title="Balance Sheet")
    assert len(chunks) == 1
    assert chunks[0].content_type == CONTENT_TABLE


def test_section_classification_mdna():
    chunks = chunk_narrative("Some discussion.", section_title="Management Discussion and Analysis")
    assert chunks[0].content_type == CONTENT_MDNA


def test_chunk_document_mixed():
    secs = [
        {"text": "Narrative here about the business.", "title": "Overview", "page_number": 1},
        {"text": "| x | y |", "title": "Table 1", "is_table": True, "page_number": 2},
    ]
    chunks = chunk_document(secs)
    assert any(c.content_type == CONTENT_TABLE for c in chunks)


# ---- citations / grounding ----------------------------------------------
def test_citation_render_prefers_label_then_page():
    c = Citation("Infosys", "FY2023-24", "Annual Report", page_number=148, page_label="146",
                 section="Notes to Accounts")
    out = c.render()
    assert "printed p.146" in out
    c2 = Citation("Infosys", "FY2023-24", "Annual Report", page_number=148, page_label=None)
    assert "PDF page 148" in c2.render()


def test_grounding_exact_and_absent():
    ev = ["Revenue from operations grew to 1500 crore during the year."]
    assert passage_is_grounded("revenue from operations grew to 1500 crore", ev).supported
    assert not passage_is_grounded("the company plans a merger with Acme Corp", ev).supported


def test_numbers_supported_rejects_fabricated():
    ev = ["Profit after tax was 250 crore."]
    assert numbers_supported("PAT was 250 crore", ev).supported
    assert not numbers_supported("PAT was 999 crore", ev).supported
    assert extract_numbers("1,234.5 and 6") == [1234.5, 6.0]


# ---- retrieval filter ----------------------------------------------------
def test_retrieval_filter_matches():
    f = RetrievalFilter(company_names=["Infosys"], financial_years=["FY2023-24"])
    assert f.matches({"company_name": "Infosys", "financial_year": "FY2023-24"})
    assert not f.matches({"company_name": "TCS", "financial_year": "FY2023-24"})


def test_extract_financial_years():
    ys = extract_financial_years("Compare FY2022-23 and FY24 revenue")
    assert "FY2022-23" in ys
    assert any(y.startswith("FY2024") for y in ys)


def test_dedupe_order():
    assert dedupe_preserving_order(["a", "b", "a", "c"]) == ["a", "b", "c"]


# ---- hybrid search -------------------------------------------------------
def test_bm25_and_rrf():
    ids = ["d1", "d2", "d3"]
    texts = [
        "operating margin declined due to higher input costs",
        "revenue grew across all segments",
        "contingent liabilities and related party transactions",
    ]
    idx = BM25Index(ids, texts)
    res = idx.search("operating margin costs", top_k=3)
    assert res and res[0].doc_id == "d1"

    dense = [ScoredDoc("d2", 0.9), ScoredDoc("d1", 0.8)]
    kw = [ScoredDoc("d1", 5.0), ScoredDoc("d3", 1.0)]
    fused = reciprocal_rank_fusion([dense, kw], top_k=3)
    assert fused[0].doc_id == "d1"  # appears high in both


# ---- risk flags ----------------------------------------------------------
def test_risk_flags_are_signals_with_rationale():
    flags = scan_text("There is material uncertainty related to going concern and pending litigation.")
    cats = {f.category for f in flags}
    assert "going_concern" in cats
    assert "litigation" in cats
    assert all(f.severity == "review" for f in flags)
    assert all("not a conclusion" in f.rationale for f in flags)


# ---- comparisons ---------------------------------------------------------
def test_trend_reports_missing_years_without_inventing():
    fs = FinancialFactSet()
    fs.add(FinancialFact("Infosys", "FY2022-23", "revenue", 1000.0, basis="consolidated"))
    trend = build_trend(fs, "Infosys", "revenue", ["FY2021-22", "FY2022-23"], "consolidated")
    pts = {p.financial_year: p for p in trend.points}
    assert pts["FY2021-22"].value is None and not pts["FY2021-22"].available
    assert pts["FY2022-23"].value == 1000.0
    assert "FY2021-22" in trend.missing_years


def test_peer_comparison_warns_on_mixed_basis():
    fs = FinancialFactSet()
    fs.add(FinancialFact("A", "FY2023-24", "revenue", 100.0, basis="consolidated"))
    fs.add(FinancialFact("B", "FY2023-24", "revenue", 200.0, basis="standalone"))
    pc = compare_peers(fs, ["A", "B"], "revenue", "FY2023-24",
                       bases={"A": "consolidated", "B": "standalone"})
    assert any("different reporting bases" in w for w in pc.warnings)


# ---- metadata store ------------------------------------------------------
def test_store_idempotent_upsert_and_dedup(tmp_path):
    db = str(tmp_path / "t.db")
    store = MetadataStore(db)
    doc = DocumentMetadata(document_id="d1", company_name="Infosys", financial_year="FY2023-24",
                           source_filename="x.pdf", document_hash="hash123")
    store.upsert_document(doc)
    store.upsert_document(doc)  # again -> no duplicate
    assert len(store.list_documents()) == 1
    assert "hash123" in store.known_hashes()
    assert store.find_by_hash("hash123")["company_name"] == "Infosys"
    assert store.stats()["documents"] == 1


def test_store_cache_and_queries(tmp_path):
    store = MetadataStore(str(tmp_path / "t.db"))
    store.cache_put("h1", "q", "resp")
    assert store.cache_get("h1") == "resp"
    store.log_query("what is revenue?")
    assert "what is revenue?" in store.recent_queries()
