"""Narrative-track parsers: DOCX, plain markdown/text, and PDF prose.

PDF table extraction has its own module (``tables.py``) because of the
two-extractor confidence check. Here we only deal with the prose part of
a PDF and leave table placeholders where the tables are, which
``ingest.pipeline`` fills in later.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParseResult:
    markdown: str
    extractor: str
    confidence: float
    note: str | None = None


# ---------- DOCX ----------
def parse_docx(path: Path) -> ParseResult:
    from docx import Document
    doc = Document(str(path))
    lines: list[str] = []
    for p in doc.paragraphs:
        txt = p.text.rstrip()
        if not txt:
            lines.append("")
            continue
        style = (p.style.name or "").lower() if p.style else ""
        if style.startswith("heading"):
            # heading 1 / heading 2 / ...
            depth = _depth_from_style(style, default=2)
            lines.append(f"{'#' * depth} {txt}")
        elif style.startswith("list"):
            lines.append(f"- {txt}")
        else:
            lines.append(txt)
    # Tables inside docx are rendered as pipe-tables in the narrative; the
    # ingest pipeline does NOT split them off to the numeric track because
    # docx tables lack typed cells. Phase 4 can revisit if we see demand.
    for t in doc.tables:
        lines.append("")
        rows = [[cell.text.strip() for cell in row.cells] for row in t.rows]
        if rows:
            header = rows[0]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("|" + "|".join([" --- "] * len(header)) + "|")
            for r in rows[1:]:
                # Pad short rows so Markdown stays well-formed.
                padded = r + [""] * max(0, len(header) - len(r))
                lines.append("| " + " | ".join(padded[:len(header)]) + " |")
    md = "\n".join(lines).strip() + "\n"
    return ParseResult(markdown=md, extractor="docx", confidence=0.95)


def _depth_from_style(style: str, *, default: int) -> int:
    for ch in style:
        if ch.isdigit():
            return min(6, max(1, int(ch)))
    return default


# ---------- Plain text / markdown ----------
def parse_plaintext(path: Path) -> ParseResult:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # markdown passes through; txt gets a filename H1 so the chunker has
    # something structural to anchor on.
    if path.suffix.lower() == ".md":
        return ParseResult(markdown=raw, extractor="plaintext", confidence=1.0)
    md = f"# {path.stem}\n\n{raw}\n"
    return ParseResult(markdown=md, extractor="plaintext", confidence=1.0)


# ---------- PDF prose ----------
def parse_pdf_prose(path: Path) -> ParseResult:
    """Extract text from a PDF, page by page, as a single markdown document.

    Does NOT attempt table extraction here — that's ``ingest.tables`` with
    its own confidence check. Tables inside a page's text layer come out
    as free-form text here, which is fine for the narrative track; the
    numeric track gets its chance separately.
    """
    import pdfplumber  # local import so audit/import boundary stays clean
    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            pages.append(f"## Page {i}\n\n{txt.strip()}\n")
    md = "\n\n".join(pages).strip() + "\n"
    # Confidence for PDF prose extraction: pdfplumber is reliable on
    # text-layer PDFs. We don't score page-by-page here; the ingest log
    # just records the single number.
    return ParseResult(markdown=md, extractor="pdfplumber",
                       confidence=0.9 if md.strip() else 0.3,
                       note=None if md.strip() else "empty text layer")
