"""Optional Docling integration (configured primary high-fidelity parser).

Docling is import-guarded so the application remains fully usable without it
(the pdfplumber path in :mod:`src.ingestion.parser` is the working default).
Docling pulls heavyweight dependencies (PyTorch, layout/OCR models) that are
intentionally NOT auto-installed on a 16 GB machine — see docs/limitations.md.

When installed, this uses Docling's documented ``DocumentConverter`` API and
exports both Markdown and the structured DoclingDocument JSON for provenance.
"""
from __future__ import annotations

from pathlib import Path

from src.ingestion.parser import ParsedDocument, ParsedPage, ParsedSection
from src.utils.errors import ParsingError


def docling_available() -> bool:
    try:
        import docling  # noqa: F401

        return True
    except Exception:
        return False


def parse_pdf_with_docling(path: str | Path) -> ParsedDocument:
    """Parse a PDF with Docling, exporting Markdown + structured JSON.

    Raises :class:`ParsingError` if Docling is not installed so the caller can
    fall back to pdfplumber.
    """
    try:
        from docling.document_converter import DocumentConverter
    except Exception as exc:  # pragma: no cover - optional dep
        raise ParsingError(f"Docling not installed: {exc}") from exc

    p = Path(path)
    try:
        converter = DocumentConverter()
        result = converter.convert(str(p))
        doc = result.document
        markdown = doc.export_to_markdown()
        try:
            structured = doc.export_to_dict()
        except Exception:
            structured = None
        version = _version()
    except Exception as exc:
        raise ParsingError(f"Docling failed on {p.name}: {exc}") from exc

    sections = [ParsedSection(text=markdown)] if markdown.strip() else []
    warnings = [] if markdown.strip() else ["Docling produced no text (possible scan/OCR issue)."]
    return ParsedDocument(
        source_path=str(p), parser_name="docling", parser_version=version,
        markdown=markdown, pages=[], sections=sections, structured=structured, warnings=warnings,
    )


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("docling")
    except Exception:
        return "unknown"
