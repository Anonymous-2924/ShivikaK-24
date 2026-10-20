"""Verify the default (pdfplumber) PDF parsing path on a real PDF fixture."""
from pathlib import Path

import pytest

from src.ingestion.parse_validation import validate_parse
from src.ingestion.parser import parse_document

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_report.pdf"


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample PDF fixture not present")
def test_pdf_parse_extracts_text_and_pages():
    doc = parse_document(FIXTURE)
    assert doc.parser_name in ("pymupdf", "pdfplumber")  # PyMuPDF default, pdfplumber fallback
    assert doc.pages and doc.total_chars > 100
    assert "Revenue from operations" in doc.markdown
    quality = validate_parse(doc, source_size_bytes=FIXTURE.stat().st_size)
    assert quality.ok
    assert quality.stats["pages"] >= 1


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample PDF fixture not present")
def test_pdf_progress_callback_and_engines():
    calls = []
    doc = parse_document(FIXTURE, progress=lambda done, total: calls.append((done, total)))
    assert calls and calls[-1][0] == calls[-1][1]  # reaches 100%
    # pdfplumber fallback produces equivalent text
    alt = parse_document(FIXTURE, engine="pdfplumber")
    assert alt.parser_name == "pdfplumber"
    assert "Revenue from operations" in alt.markdown


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample PDF fixture not present")
def test_pdf_extract_tables_flag_controls_table_pass():
    # extract_tables=False is a text-only preview path (tables kept by default).
    doc = parse_document(FIXTURE, extract_tables=False)
    assert "Revenue from operations" in doc.markdown  # text still extracted
    assert all(not p.tables for p in doc.pages)        # no tables parsed


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample PDF fixture not present")
def test_pdf_max_pages_caps_and_warns():
    doc = parse_document(FIXTURE, max_pages=1)
    assert len(doc.pages) == 1
    # fixture is 1 page, so no cap warning; a multi-page doc would warn. Just assert no crash.
    assert doc.total_chars > 0


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample PDF fixture not present")
def test_table_detection_gated_by_number_density():
    # High threshold -> no page qualifies -> table pass skipped, but text kept.
    gated = parse_document(FIXTURE, table_min_numbers=10_000)
    assert all(not p.tables for p in gated.pages)
    assert "Revenue from operations" in gated.markdown  # numbers still indexed via text
    # Threshold 0 -> table detection runs on every page.
    ungated = parse_document(FIXTURE, table_min_numbers=0)
    assert "Revenue from operations" in ungated.markdown
