"""End-to-end ingestion: parse -> validate -> chunk -> index.

Ties together the parser, parse validation, chunking and the RAG index, writing
document + chunk metadata with full provenance. Processes one document at a time
to respect the memory budget (no retaining multiple full documents).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.ingestion.markdown_export import export_parsed
from src.ingestion.metadata import (
    ChunkMetadata, DocumentMetadata, IndexStatus, ParseStatus, VerificationStatus,
)
from src.ingestion.parse_validation import validate_parse
from src.ingestion.parser import parse_document
from src.rag.chunking import chunk_document
from src.rag.indexing import RagIndex
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class IngestionResult:
    document_id: str
    chunks_indexed: int
    parse_warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error: str | None = None


def ingest_document(
    doc: DocumentMetadata, index: RagIndex, *, parsed_dir: str,
    chunk_size: int = 1000, chunk_overlap: int = 150, prefer_docling: bool = False,
    extract_tables: bool = True, max_pages: int = 0,
) -> IngestionResult:
    """Parse and index a single document. Updates ``doc`` status in place."""
    try:
        parsed = parse_document(doc.local_path, prefer_docling=prefer_docling,
                                extract_tables=extract_tables, max_pages=max_pages)
    except Exception as exc:
        doc.parse_status = ParseStatus.FAILED
        doc.warnings.append(f"Parse failed: {exc}")
        return IngestionResult(doc.document_id, 0, ok=False, error=str(exc))

    quality = validate_parse(parsed, source_size_bytes=doc.file_size_bytes)
    doc.parser_name = parsed.parser_name
    doc.parser_version = parsed.parser_version
    doc.warnings.extend(quality.warnings)
    export_parsed(parsed, parsed_dir, doc.document_id)

    if not quality.ok:
        doc.parse_status = ParseStatus.FAILED
        return IngestionResult(doc.document_id, 0, quality.warnings, ok=False,
                               error="Empty/failed extraction.")
    doc.parse_status = ParseStatus.PARSED

    sections = [
        {"text": s.text, "title": s.title, "page_number": s.page_number,
         "page_label": s.page_label, "is_table": s.is_table}
        for s in parsed.sections
    ]
    chunks = chunk_document(sections, chunk_size=chunk_size, overlap=chunk_overlap)

    records = []
    for i, ch in enumerate(chunks):
        chunk_id = f"{doc.document_id}:{i}"
        meta = ChunkMetadata.from_document(
            doc, chunk_id=chunk_id, section_title=ch.section_title,
            page_number=ch.page_number, page_label=ch.page_label, content_type=ch.content_type,
        )
        records.append({"chunk_id": chunk_id, "document_id": doc.document_id,
                        "text": ch.text, "metadata": meta.model_dump()})

    try:
        n = index.index_chunks(records)
        doc.index_status = IndexStatus.INDEXED
    except Exception as exc:
        doc.index_status = IndexStatus.FAILED
        doc.warnings.append(f"Indexing failed: {exc}")
        return IngestionResult(doc.document_id, 0, quality.warnings, ok=False, error=str(exc))

    return IngestionResult(doc.document_id, n, quality.warnings, ok=True)
