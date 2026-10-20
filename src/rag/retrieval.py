"""Retrieval filtering and query normalization.

The metadata filter logic here is pure and fully testable; it's used both by
the Qdrant-backed retriever and by in-memory tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RetrievalFilter:
    """Structured filter over chunk metadata."""

    company_ids: Optional[list[str]] = None
    company_names: Optional[list[str]] = None
    financial_years: Optional[list[str]] = None
    report_types: Optional[list[str]] = None
    content_types: Optional[list[str]] = None
    basis: Optional[str] = None  # standalone | consolidated

    def matches(self, meta: dict) -> bool:
        """Return True if a chunk's metadata satisfies every set facet."""
        def _in(value, allowed):
            if not allowed:
                return True
            return value in allowed

        if self.company_ids and meta.get("company_id") not in self.company_ids:
            return False
        if self.company_names:
            name = (meta.get("company_name") or "").lower()
            if name not in [c.lower() for c in self.company_names]:
                return False
        if not _in(meta.get("financial_year"), self.financial_years):
            return False
        if not _in(meta.get("report_type"), self.report_types):
            return False
        if not _in(meta.get("content_type"), self.content_types):
            return False
        if self.basis and meta.get("basis") not in (self.basis, None, "unknown"):
            return False
        return True


_FY_RE = re.compile(r"\bFY\s?(\d{2,4})(?:[-/](\d{2,4}))?\b", re.IGNORECASE)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip())


def extract_financial_years(query: str) -> list[str]:
    """Pull FY references like 'FY2023-24', 'FY23', 'FY 2022' from a query."""
    out: list[str] = []
    for m in _FY_RE.finditer(query):
        start, end = m.group(1), m.group(2)
        if len(start) == 2:
            start = "20" + start
        if end and len(end) == 2:
            end = start[:2] + end
        out.append(f"FY{start}-{end[-2:]}" if end else f"FY{start}")
    return out


def dedupe_preserving_order(doc_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for d in doc_ids:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out
