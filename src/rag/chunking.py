"""Structure-aware chunking.

Different content types get different strategies. Table chunks are kept whole
(never split away from their headers); narrative text is split with overlap.
All chunks carry provenance via :class:`~src.ingestion.metadata.ChunkMetadata`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

CONTENT_NARRATIVE = "narrative"
CONTENT_TABLE = "table"
CONTENT_NOTES = "notes"
CONTENT_MDNA = "mdna"
CONTENT_AUDITOR = "auditor"


@dataclass
class Chunk:
    text: str
    content_type: str = CONTENT_NARRATIVE
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    page_label: Optional[str] = None


def classify_section(title: str | None) -> str:
    """Heuristically classify a section by its heading."""
    if not title:
        return CONTENT_NARRATIVE
    t = title.lower()
    if "management discussion" in t or "md&a" in t or "mdna" in t:
        return CONTENT_MDNA
    if "auditor" in t or "independent auditors" in t:
        return CONTENT_AUDITOR
    if "notes to" in t or t.strip().startswith("note "):
        return CONTENT_NOTES
    return CONTENT_NARRATIVE


def _split_sentences(text: str) -> list[str]:
    # Lightweight splitter: avoids a heavy NLP dependency while respecting
    # sentence-ish boundaries so chunks don't cut mid-sentence.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text.strip())
    return [p for p in parts if p]


def chunk_narrative(
    text: str,
    *,
    chunk_size: int = 1000,
    overlap: int = 150,
    section_title: str | None = None,
    page_number: int | None = None,
    page_label: str | None = None,
) -> list[Chunk]:
    """Split narrative text into overlapping chunks by character budget.

    Overlap is measured in characters and carried from the end of the previous
    chunk, so retrieval context isn't lost at boundaries.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size - 1))
    content_type = classify_section(section_title)

    text = text.strip()
    if not text:
        return []

    sentences = _split_sentences(text)
    chunks: list[str] = []
    buf = ""
    for sent in sentences:
        if not buf:
            buf = sent
        elif len(buf) + 1 + len(sent) <= chunk_size:
            buf = f"{buf} {sent}"
        else:
            chunks.append(buf)
            # carry overlap tail
            tail = buf[-overlap:] if overlap else ""
            buf = (tail + " " + sent).strip() if tail else sent
    if buf:
        chunks.append(buf)

    # A single very long sentence can exceed chunk_size; hard-split those.
    out: list[Chunk] = []
    for c in chunks:
        if len(c) <= chunk_size * 1.5:
            out.append(Chunk(c, content_type, section_title, page_number, page_label))
        else:
            for i in range(0, len(c), chunk_size - overlap):
                out.append(
                    Chunk(c[i : i + chunk_size], content_type, section_title, page_number, page_label)
                )
    return out


def chunk_table(
    markdown_table: str,
    *,
    section_title: str | None = None,
    page_number: int | None = None,
    page_label: str | None = None,
) -> list[Chunk]:
    """Keep a table as a single coherent chunk, preserving header rows."""
    text = markdown_table.strip()
    if not text:
        return []
    return [Chunk(text, CONTENT_TABLE, section_title, page_number, page_label)]


def chunk_document(
    sections: Iterable[dict],
    *,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[Chunk]:
    """Chunk a parsed document.

    ``sections`` is an iterable of dicts with keys: ``text``, ``title``
    (optional), ``page_number`` (optional), ``page_label`` (optional),
    ``is_table`` (optional bool).
    """
    result: list[Chunk] = []
    for sec in sections:
        title = sec.get("title")
        page = sec.get("page_number")
        label = sec.get("page_label")
        if sec.get("is_table"):
            result.extend(chunk_table(sec.get("text", ""), section_title=title,
                                      page_number=page, page_label=label))
        else:
            result.extend(
                chunk_narrative(
                    sec.get("text", ""),
                    chunk_size=chunk_size,
                    overlap=overlap,
                    section_title=title,
                    page_number=page,
                    page_label=label,
                )
            )
    return result
