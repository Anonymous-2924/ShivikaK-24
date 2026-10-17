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
