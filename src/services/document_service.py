"""Document ingestion service: upload/validate/parse/index with provenance."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.ingestion.file_validation import is_duplicate, safe_filename, validate_file
from src.ingestion.metadata import DocumentMetadata, make_document_id
from src.rag.ingestion_pipeline import IngestionResult, ingest_document
from src.services.context import AppContext
from src.utils.errors import ValidationError


@dataclass
class AddDocumentOutcome:
    document: DocumentMetadata
    result: Optional[IngestionResult]
    duplicate: bool = False
    message: str = ""


class DocumentService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    def add_file(self, src_path: str, *, company_name: str, financial_year: Optional[str] = None,
                 report_type: Optional[str] = None, basis: str = "unknown",
                 source_url: Optional[str] = None, exchange: Optional[str] = None,
                 index_now: bool = True) -> AddDocumentOutcome:
        info = validate_file(src_path, max_mb=self.ctx.settings.max_download_mb)
        known = self.ctx.metadata_store.known_hashes()
        if is_duplicate(info.sha256, known):
            existing = self.ctx.metadata_store.find_by_hash(info.sha256)
            return AddDocumentOutcome(
                document=DocumentMetadata(**_doc_kwargs(existing)) if existing else None,  # type: ignore
                result=None, duplicate=True,
                message="Duplicate content (same SHA-256) — not re-ingested.",
            )

        raw_dir = self.ctx.settings.paths()["raw"]
        raw_dir.mkdir(parents=True, exist_ok=True)
        dest = raw_dir / safe_filename(Path(src_path).name)
        if Path(src_path).resolve() != dest.resolve():
            shutil.copy2(src_path, dest)

        doc_id = make_document_id(company_name, financial_year, info.sha256)
        from src.ingestion.metadata import ReportBasis
        doc = DocumentMetadata(
            document_id=doc_id, company_name=company_name, financial_year=financial_year,
            report_type=report_type, basis=ReportBasis(basis) if basis in
            {b.value for b in ReportBasis} else ReportBasis.UNKNOWN,
            exchange=exchange, source_url=source_url, source_filename=Path(src_path).name,
            local_path=str(dest), document_hash=info.sha256, file_size_bytes=info.size_bytes,
        )

        result = None
        if index_now:
            result = ingest_document(
                doc, self.ctx.index, parsed_dir=str(self.ctx.settings.paths()["parsed"]),
                chunk_size=self.ctx.settings.chunk_size,
                chunk_overlap=self.ctx.settings.chunk_overlap,
            )
        self.ctx.metadata_store.upsert_document(doc)
        return AddDocumentOutcome(document=doc, result=result,
                                  message="Ingested." if (result and result.ok) else "Stored.")

    def list_documents(self) -> list[dict]:
        return self.ctx.metadata_store.list_documents()

    def delete_document(self, document_id: str, *, remove_file: bool = False) -> None:
        doc = self.ctx.metadata_store.get_document(document_id)
        self.ctx.index.delete_document(document_id)
        self.ctx.metadata_store.delete_document(document_id)
        if remove_file and doc and doc.get("local_path"):
            Path(doc["local_path"]).unlink(missing_ok=True)


def _doc_kwargs(row: dict) -> dict:
    allowed = set(DocumentMetadata.model_fields.keys())
    return {k: v for k, v in row.items() if k in allowed}
