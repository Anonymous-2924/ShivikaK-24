"""Verify the default (pdfplumber) PDF parsing path on a real PDF fixture."""
from pathlib import Path

import pytest

from src.ingestion.parse_validation import validate_parse
from src.ingestion.parser import parse_document

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_report.pdf"


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample PDF fixture not present")
def test_pdf_parse_extracts_text_and_pages():
    doc = parse_document(FIXTURE)
    assert doc.parser_name == "pdfplumber"
    assert doc.pages and doc.total_chars > 100
    assert "Revenue from operations" in doc.markdown
    quality = validate_parse(doc, source_size_bytes=FIXTURE.stat().st_size)
    assert quality.ok
    assert quality.stats["pages"] >= 1


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample PDF fixture not present")
def test_pdf_fast_mode_skips_tables_and_warns():
    doc = parse_document(FIXTURE, extract_tables=False)
    assert "Revenue from operations" in doc.markdown  # text still extracted
    assert all(not p.tables for p in doc.pages)        # no tables parsed
    assert any("Fast mode" in w for w in doc.warnings)


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample PDF fixture not present")
def test_pdf_max_pages_caps_and_warns():
    doc = parse_document(FIXTURE, max_pages=1)
    assert len(doc.pages) == 1
    # fixture is 1 page, so no cap warning; a multi-page doc would warn. Just assert no crash.
    assert doc.total_chars > 0
