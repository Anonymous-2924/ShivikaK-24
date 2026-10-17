"""Extract financial-statement tables from parsed sections with context.

Preserves table title, row/column labels, units and source page so values stay
interpretable. Does NOT auto-map line items to metrics via an LLM — mapping is
explicit and reviewable (see finance.financial_data / the Financial Analysis UI).
"""
from __future__ import annotations

import re
from typing import Optional

from src.ingestion.metadata import TableContext
from src.ingestion.parser import ParsedDocument, ParsedSection

_UNIT_RE = re.compile(r"(?:in\s+)?(₹|rs\.?|inr|usd)\s*(crore|cr|lakh|lacs|million|mn|billion|bn)?",
                      re.IGNORECASE)


def detect_units(text: str) -> Optional[str]:
    m = _UNIT_RE.search(text)
    if not m:
        return None
    cur = m.group(1)
    scale = m.group(2) or ""
    return f"{cur} {scale}".strip()


def table_to_context(section: ParsedSection) -> TableContext:
    rows = [r for r in section.text.splitlines() if r.strip().startswith("|")]
    col_labels: list[str] = []
    row_labels: list[str] = []
    if rows:
        header_cells = [c.strip() for c in rows[0].strip("|").split("|")]
        col_labels = [c for c in header_cells if c]
        for r in rows[2:]:  # skip header + separator
            cells = [c.strip() for c in r.strip("|").split("|")]
            if cells and cells[0]:
                row_labels.append(cells[0])
    return TableContext(
        table_title=section.title,
        row_labels=row_labels,
        column_labels=col_labels,
        units=detect_units(section.text),
        page_number=section.page_number,
    )


def extract_tables(doc: ParsedDocument) -> list[TableContext]:
    return [table_to_context(s) for s in doc.sections if s.is_table]
