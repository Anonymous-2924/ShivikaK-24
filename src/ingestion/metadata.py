"""Normalized metadata schema for documents, chunks and financial tables.

Provenance is preserved through every transformation. Unknown/unverifiable
information is represented explicitly (``None`` / :class:`VerificationStatus`)
rather than being guessed.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    NOT_AVAILABLE = "not_available"
    CONFLICTING = "conflicting"
    AMBIGUOUS = "ambiguous"


class DocumentType(str, Enum):
    ANNUAL_REPORT = "annual_report"
    QUARTERLY_RESULT = "quarterly_result"
    INVESTOR_PRESENTATION = "investor_presentation"
    TRANSCRIPT = "transcript"
    OTHER = "other"


class ReportBasis(str, Enum):
    STANDALONE = "standalone"
    CONSOLIDATED = "consolidated"
    UNKNOWN = "unknown"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"


class IndexStatus(str, Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"
    STALE = "stale"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentMetadata(BaseModel):
    """Metadata for one source document (an annual report or upload)."""

    document_id: str
    company_id: Optional[str] = None
    company_name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None  # NSE / BSE / None
    financial_year: Optional[str] = None  # e.g. "FY2023-24"
    period_start: Optional[str] = None  # ISO date, if verifiable
    period_end: Optional[str] = None
    document_type: DocumentType = DocumentType.ANNUAL_REPORT
    report_type: Optional[str] = None  # free text, e.g. "Integrated Annual Report"
    basis: ReportBasis = ReportBasis.UNKNOWN
    publication_date: Optional[str] = None
    source_url: Optional[str] = None
    source_filename: str
    local_path: Optional[str] = None
    document_hash: Optional[str] = None  # SHA-256 of the original file
    file_size_bytes: Optional[int] = None
    download_timestamp: Optional[str] = None
    parser_name: Optional[str] = None
    parser_version: Optional[str] = None
    parse_status: ParseStatus = ParseStatus.PENDING
    index_status: IndexStatus = IndexStatus.PENDING
    verification_status: VerificationStatus = VerificationStatus.NOT_VERIFIED
    warnings: list[str] = Field(default_factory=list)
    ingestion_timestamp: str = Field(default_factory=_now)

    def citation_label(self) -> str:
        """Human-readable citation stem, e.g. 'Infosys — FY2023-24 — Annual Report'."""
        parts = [self.company_name]
        if self.financial_year:
            parts.append(self.financial_year)
        parts.append(self.report_type or self.document_type.value.replace("_", " ").title())
        return " — ".join(parts)


class ChunkMetadata(BaseModel):
    """Metadata attached to every indexed chunk/node."""

    chunk_id: str
    document_id: str
    company_id: Optional[str] = None
    company_name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    financial_year: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    document_type: str = DocumentType.ANNUAL_REPORT.value
    report_type: Optional[str] = None
    basis: str = ReportBasis.UNKNOWN.value
    section_title: Optional[str] = None
    section_path: Optional[str] = None
    # Physical PDF page index (0/1-based as produced by the parser) vs the
    # printed page label. We never conflate the two.
    page_number: Optional[int] = None
    page_label: Optional[str] = None
    source_url: Optional[str] = None
    source_filename: Optional[str] = None
    content_type: str = "narrative"  # narrative | table | notes | mdna | auditor
    parser_name: Optional[str] = None
    parser_version: Optional[str] = None
    document_hash: Optional[str] = None
    verification_status: str = VerificationStatus.NOT_VERIFIED.value
    ingestion_timestamp: str = Field(default_factory=_now)

    @classmethod
    def from_document(cls, doc: DocumentMetadata, *, chunk_id: str, **overrides) -> "ChunkMetadata":
        base = dict(
            chunk_id=chunk_id,
            document_id=doc.document_id,
            company_id=doc.company_id,
            company_name=doc.company_name,
            ticker=doc.ticker,
            exchange=doc.exchange,
            financial_year=doc.financial_year,
            period_start=doc.period_start,
            period_end=doc.period_end,
            document_type=doc.document_type.value,
            report_type=doc.report_type,
            basis=doc.basis.value,
            source_url=doc.source_url,
            source_filename=doc.source_filename,
            parser_name=doc.parser_name,
            parser_version=doc.parser_version,
            document_hash=doc.document_hash,
        )
        base.update(overrides)
        return cls(**base)


class TableContext(BaseModel):
    """Preserved context for a financial table so values stay interpretable."""

    table_title: Optional[str] = None
    row_labels: list[str] = Field(default_factory=list)
    column_labels: list[str] = Field(default_factory=list)
    units: Optional[str] = None
    currency: Optional[str] = None
    periods: list[str] = Field(default_factory=list)
    page_number: Optional[int] = None
    note_number: Optional[str] = None


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_document_id(company_name: str, financial_year: str | None, file_hash: str) -> str:
    """Stable document id from company + FY + content hash (idempotent ingestion)."""
    stem = f"{company_name.strip().lower()}|{(financial_year or 'na').lower()}|{file_hash[:16]}"
    return hashlib.sha1(stem.encode("utf-8")).hexdigest()[:20]
