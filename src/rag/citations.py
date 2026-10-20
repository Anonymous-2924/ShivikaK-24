"""Citation model and anti-hallucination grounding checks.

A citation points back to a specific place in a specific report. The grounding
verifier checks that quoted text actually appears in retrieved evidence and
that numeric claims are supported — the core defence against fabrication.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional


@dataclass
class Citation:
    company_name: str
    financial_year: Optional[str]
    report_type: Optional[str]
    page_number: Optional[int]  # physical PDF page index (fallback)
    page_label: Optional[str]  # printed page number, if reliably known
    section: Optional[str] = None
    note_number: Optional[str] = None
    source_filename: Optional[str] = None
    source_url: Optional[str] = None
    document_id: Optional[str] = None
    passage: Optional[str] = None  # supporting text / table reference

    def render(self) -> str:
        """Render as '[Company] — [FY] — [Report] — [PDF page] — [Section]'."""
        parts = [self.company_name]
        if self.financial_year:
            parts.append(self.financial_year)
        parts.append(self.report_type or "Document")
        if self.page_label:
            parts.append(f"printed p.{self.page_label}")
        elif self.page_number is not None:
            parts.append(f"PDF page {self.page_number}")
        if self.section:
            parts.append(self.section)
        if self.note_number:
            parts.append(f"Note {self.note_number}")
        return " — ".join(parts)


@dataclass
class GroundingReport:
    supported: bool
    score: float  # best similarity found, 0..1
    matched_passage: Optional[str] = None
    details: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def passage_is_grounded(
    quote: str, evidence_texts: list[str], *, threshold: float = 0.82
) -> GroundingReport:
    """Check that ``quote`` is substantively present in the evidence.

    Uses normalized substring match first (exact grounding), then a fuzzy
    ratio over a sliding window as a fallback. Returns the best score found.
    """
    q = _normalize(quote)
    if not q:
        return GroundingReport(False, 0.0, details=["Empty quote."])

    best = 0.0
    best_src: Optional[str] = None
    for ev in evidence_texts:
        e = _normalize(ev)
        if not e:
            continue
        if q in e:
            return GroundingReport(True, 1.0, matched_passage=ev,
                                   details=["Exact normalized substring match."])
        # fuzzy windowed comparison
        window = len(q)
        step = max(1, window // 2)
        for i in range(0, max(1, len(e) - window + 1), step):
            ratio = SequenceMatcher(None, q, e[i : i + window]).ratio()
            if ratio > best:
                best, best_src = ratio, ev
    supported = best >= threshold
    return GroundingReport(
        supported,
        round(best, 3),
        matched_passage=best_src if supported else None,
        details=[f"Best fuzzy similarity {best:.3f} (threshold {threshold})."],
    )


_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def extract_numbers(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUM_RE.findall(text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return out


def numbers_supported(
    claim: str, evidence_texts: list[str], *, rel_tol: float = 0.01
) -> GroundingReport:
    """Every number in ``claim`` must appear (within tolerance) in evidence."""
    claim_nums = extract_numbers(claim)
    if not claim_nums:
        return GroundingReport(True, 1.0, details=["No numeric claims to verify."])
    evidence_nums = [n for ev in evidence_texts for n in extract_numbers(ev)]
    unmatched: list[float] = []
    for cn in claim_nums:
        ok = any(
            abs(cn - en) <= max(rel_tol * max(abs(cn), abs(en)), 1e-9) for en in evidence_nums
        )
        if not ok:
            unmatched.append(cn)
    if unmatched:
        return GroundingReport(
            False, 0.0,
            details=[f"Unsupported number(s) in claim: {unmatched}"],
        )
    return GroundingReport(True, 1.0, details=["All claim numbers found in evidence."])


ABSTENTION_MESSAGE = (
    "The indexed reports do not contain sufficient evidence to answer this "
    "question. No figure or statement has been inferred. Please add the "
    "relevant annual report, or rephrase the question."
)
