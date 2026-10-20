"""Document parsing with page/section provenance.

Dispatches by file type. The default PDF path uses ``pdfplumber`` (CPU-only,
no model downloads) and preserves per-page text and tables. Docling is the
configured *primary* parser for high-fidelity conversion but is optional at
runtime (see :mod:`src.ingestion.docling_parser`); when it is installed and
enabled it is preferred for PDFs.

Every parse returns a :class:`ParsedDocument` with explicit warnings — failures
are never silently replaced with invented text.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.utils.errors import ParsingError
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class ParsedPage:
    page_number: int  # physical PDF page index (1-based)
    text: str
    page_label: Optional[str] = None  # printed label if detected, else None
    tables: list[list[list[str]]] = field(default_factory=list)


@dataclass
class ParsedSection:
    text: str
    title: Optional[str] = None
    page_number: Optional[int] = None
    page_label: Optional[str] = None
    is_table: bool = False


@dataclass
class ParsedDocument:
    source_path: str
    parser_name: str
    parser_version: str
    markdown: str
    pages: list[ParsedPage] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    structured: Optional[dict] = None  # JSON-serialisable structured rep (if any)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return len(self.markdown)


def parse_document(path: str | Path, *, prefer_docling: bool = False,
                   extract_tables: bool = True, max_pages: int = 0,
                   engine: str = "auto", progress=None,
                   table_min_numbers: int = 12) -> ParsedDocument:
    """Parse a document of any supported type into a :class:`ParsedDocument`.

    PDFs use PyMuPDF by default (``engine="auto"``) — text extraction is
    near-instant and tables are detected with ``find_tables``. pdfplumber is a
    fallback engine (``engine="pdfplumber"``, or when PyMuPDF is unavailable).

    ``extract_tables`` controls whether tables are detected (tables are the
    point of a financial report, so this defaults to True; it exists mainly for
    tests and a quick text-only preview). ``max_pages>0`` caps pages parsed.
    ``progress(done, total)`` is called per page so the UI can show real
    progress instead of an indefinite spinner.
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".pdf":
        if prefer_docling:
            try:
                from src.ingestion.docling_parser import parse_pdf_with_docling

                return parse_pdf_with_docling(p)
            except Exception as exc:  # fall back, but say so
                log.warning("Docling unavailable/failed (%s); using default PDF engine.", exc)
        use_pymupdf = engine in ("auto", "pymupdf") and _pymupdf_available()
        if use_pymupdf:
            return _parse_pdf_pymupdf(p, extract_tables=extract_tables, max_pages=max_pages,
                                      progress=progress, table_min_numbers=table_min_numbers)
        return _parse_pdf_pdfplumber(p, extract_tables=extract_tables, max_pages=max_pages,
                                     progress=progress)
    if ext in {".md", ".txt"}:
        return _parse_text(p)
    if ext == ".csv":
        return _parse_csv(p)
    if ext == ".xlsx":
        return _parse_xlsx(p)
    if ext == ".docx":
        return _parse_docx(p)
    raise ParsingError(f"No parser for extension '{ext}'.")


def _pymupdf_available() -> bool:
    try:
        import pymupdf  # noqa: F401

        return True
    except Exception:
        try:
            import fitz  # noqa: F401

            return True
        except Exception:
            return False


_NUM_TOKEN_RE = re.compile(r"\d[\d,]*\.?\d*")


def _looks_number_dense(text: str, min_numbers: int) -> bool:
    """Cheap gate: does this page hold enough numbers to plausibly be a table?"""
    if min_numbers <= 0:
        return True
    return len(_NUM_TOKEN_RE.findall(text)) >= min_numbers


# ---- PDF (PyMuPDF — default, fast) --------------------------------------
def _parse_pdf_pymupdf(p: Path, *, extract_tables: bool = True, max_pages: int = 0,
                       progress=None, table_min_numbers: int = 12) -> ParsedDocument:
    try:
        import pymupdf  # modern name
    except Exception:  # pragma: no cover
        import fitz as pymupdf  # legacy name

    pages: list[ParsedPage] = []
    sections: list[ParsedSection] = []
    md_parts: list[str] = []
    warnings: list[str] = []
    table_pages = 0
    try:
        doc = pymupdf.open(str(p))
        version = getattr(pymupdf, "__version__", "unknown")
        total = doc.page_count
        limit = min(total, max_pages) if max_pages and max_pages > 0 else total
        if limit < total:
            warnings.append(f"Only the first {limit} of {total} pages were parsed (page cap).")
        for i in range(1, limit + 1):
            page = doc.load_page(i - 1)
            text = page.get_text("text") or ""
            tables = []
            # Text already contains every number; run the expensive structured
            # table detection only on number-dense pages (financial statements
            # and notes), so a 600-900 page report stays tractable.
            if extract_tables and _looks_number_dense(text, table_min_numbers):
                try:
                    tf = page.find_tables()
                    for t in tf.tables:
                        rows = t.extract()
                        if rows:
                            tables.append(rows)
                    if tables:
                        table_pages += 1
                except Exception as exc:
                    warnings.append(f"Table detection failed on page {i}: {exc}")
            pages.append(ParsedPage(i, text, None, tables))
            if text.strip():
                md_parts.append(f"\n\n<!-- page {i} -->\n{text}")
                sections.append(ParsedSection(text=text, page_number=i))
            for ti, tbl in enumerate(tables):
                md_tbl = _table_to_markdown(tbl)
                md_parts.append(f"\n\n<!-- page {i} table {ti+1} -->\n{md_tbl}")
                sections.append(ParsedSection(text=md_tbl, title=f"Table (page {i})",
                                              page_number=i, is_table=True))
            if progress:
                try:
                    progress(i, limit)
                except Exception:
                    pass
        doc.close()
        if extract_tables and table_min_numbers > 0:
            warnings.append(
                f"Structured tables extracted from {table_pages} number-dense page(s); "
                "narrative pages skipped the table pass for speed. All page text (including "
                "every figure) is indexed regardless."
            )
    except Exception as exc:
        raise ParsingError(f"Failed to parse PDF {p.name}: {exc}") from exc

    md = "".join(md_parts).strip()
    if not md:
        warnings.append(
            "No extractable text found — the PDF may be scanned/image-only. "
            "OCR (Docling/Tesseract) is required; text was NOT invented."
        )
    return ParsedDocument(
        source_path=str(p), parser_name="pymupdf", parser_version=version,
        markdown=md, pages=pages, sections=sections, warnings=warnings,
    )


# ---- PDF (pdfplumber — fallback) ----------------------------------------
def _parse_pdf_pdfplumber(p: Path, *, extract_tables: bool = True, max_pages: int = 0,
                          progress=None) -> ParsedDocument:
    try:
        import pdfplumber
    except Exception as exc:  # pragma: no cover
        raise ParsingError(f"pdfplumber not installed: {exc}") from exc

    pages: list[ParsedPage] = []
    sections: list[ParsedSection] = []
    md_parts: list[str] = []
    warnings: list[str] = []
    try:
        with pdfplumber.open(str(p)) as pdf:
            version = getattr(pdfplumber, "__version__", "unknown")
            total = len(pdf.pages)
            limit = min(total, max_pages) if max_pages and max_pages > 0 else total
            if limit < total:
                warnings.append(f"Only the first {limit} of {total} pages were parsed (page cap).")
            for i, page in enumerate(pdf.pages[:limit], start=1):
                text = page.extract_text() or ""
                label = None
                try:
                    label = str(page.page_number) if page.page_number else None
                except Exception:
                    label = None
                tables = []
                if extract_tables:
                    try:
                        tables = [t for t in (page.extract_tables() or []) if t]
                    except Exception as exc:
                        warnings.append(f"Table extraction failed on page {i}: {exc}")
                pages.append(ParsedPage(i, text, label, tables))
                if text.strip():
                    md_parts.append(f"\n\n<!-- page {i} -->\n{text}")
                    sections.append(ParsedSection(text=text, page_number=i, page_label=label))
                for ti, tbl in enumerate(tables):
                    md_tbl = _table_to_markdown(tbl)
                    md_parts.append(f"\n\n<!-- page {i} table {ti+1} -->\n{md_tbl}")
                    sections.append(
                        ParsedSection(text=md_tbl, title=f"Table (page {i})",
                                      page_number=i, page_label=label, is_table=True)
                    )
                if progress:
                    try:
                        progress(i, limit)
                    except Exception:
                        pass
    except Exception as exc:
        raise ParsingError(f"Failed to parse PDF {p.name}: {exc}") from exc

    md = "".join(md_parts).strip()
    if not md:
        warnings.append(
            "No extractable text found — the PDF may be scanned/image-only. "
            "OCR (Docling/Tesseract) is required; text was NOT invented."
        )
    return ParsedDocument(
        source_path=str(p), parser_name="pdfplumber", parser_version=version,
        markdown=md, pages=pages, sections=sections, warnings=warnings,
    )


def _table_to_markdown(table: list[list]) -> str:
    rows = [[("" if c is None else str(c)).replace("\n", " ").strip() for c in row] for row in table]
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * ncols) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
    return "\n".join([header, sep, body]) if body else "\n".join([header, sep])


# ---- plain text / markdown ----------------------------------------------
def _parse_text(p: Path) -> ParsedDocument:
    text = p.read_text(encoding="utf-8", errors="replace")
    return ParsedDocument(
        source_path=str(p), parser_name="text", parser_version="1",
        markdown=text, sections=[ParsedSection(text=text)],
        warnings=[] if text.strip() else ["Empty file."],
    )


# ---- CSV -----------------------------------------------------------------
def _parse_csv(p: Path) -> ParsedDocument:
    rows: list[list[str]] = []
    with open(p, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh):
            rows.append(row)
    md = _table_to_markdown(rows) if rows else ""
    return ParsedDocument(
        source_path=str(p), parser_name="csv", parser_version="1", markdown=md,
        sections=[ParsedSection(text=md, title=p.stem, is_table=True)] if md else [],
        structured={"rows": rows},
        warnings=[] if rows else ["Empty CSV."],
    )


# ---- XLSX (openpyxl) -----------------------------------------------------
def _parse_xlsx(p: Path) -> ParsedDocument:
    try:
        from openpyxl import load_workbook
    except Exception as exc:  # pragma: no cover
        raise ParsingError(f"openpyxl not installed: {exc}") from exc
    wb = load_workbook(filename=str(p), read_only=True, data_only=True)
    md_parts, sections = [], []
    structured: dict = {}
    for ws in wb.worksheets:
        rows = [[("" if c is None else str(c)) for c in row] for row in ws.iter_rows(values_only=True)]
        structured[ws.title] = rows
        if rows:
            md = f"\n\n## Sheet: {ws.title}\n\n" + _table_to_markdown(rows)
            md_parts.append(md)
            sections.append(ParsedSection(text=md, title=f"Sheet: {ws.title}", is_table=True))
    wb.close()
    md = "".join(md_parts).strip()
    return ParsedDocument(
        source_path=str(p), parser_name="openpyxl",
        parser_version=_safe_version("openpyxl"), markdown=md, sections=sections,
        structured=structured, warnings=[] if md else ["No sheet data."],
    )


# ---- DOCX (markitdown fallback) -----------------------------------------
def _parse_docx(p: Path) -> ParsedDocument:
    try:
        from markitdown import MarkItDown

        md = MarkItDown().convert(str(p)).text_content
        parser = "markitdown"
        ver = _safe_version("markitdown")
    except Exception as exc:
        raise ParsingError(
            f"DOCX parsing needs 'markitdown' (or 'python-docx'); not available: {exc}"
        ) from exc
    return ParsedDocument(
        source_path=str(p), parser_name=parser, parser_version=ver, markdown=md,
        sections=[ParsedSection(text=md)] if md.strip() else [],
        warnings=[] if md.strip() else ["No text extracted from DOCX."],
    )


def _safe_version(pkg: str) -> str:
    try:
        from importlib.metadata import version

        return version(pkg)
    except Exception:
        return "unknown"
