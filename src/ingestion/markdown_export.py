"""Persist parsed artifacts (Markdown + structured JSON) to disk."""
from __future__ import annotations

import json
from pathlib import Path

from src.ingestion.parser import ParsedDocument


def export_parsed(doc: ParsedDocument, parsed_dir: str | Path, document_id: str) -> dict:
    """Write <document_id>.md and <document_id>.json; return their paths."""
    parsed_dir = Path(parsed_dir)
    parsed_dir.mkdir(parents=True, exist_ok=True)
    md_path = parsed_dir / f"{document_id}.md"
    md_path.write_text(doc.markdown, encoding="utf-8")
    json_path = parsed_dir / f"{document_id}.json"
    payload = {
        "source_path": doc.source_path,
        "parser_name": doc.parser_name,
        "parser_version": doc.parser_version,
        "warnings": doc.warnings,
        "structured": doc.structured,
        "pages": [
            {"page_number": p.page_number, "page_label": p.page_label, "n_tables": len(p.tables)}
            for p in doc.pages
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return {"markdown": str(md_path), "json": str(json_path)}
