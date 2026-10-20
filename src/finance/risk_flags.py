"""Transparent, rule-based risk & disclosure flagging.

Flags are *signals for the analyst to review*, never verdicts. A keyword match
alone never labels a company distressed or fraudulent — each flag records why
it fired and requires human interpretation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RiskFlag:
    category: str
    matched_term: str
    snippet: str
    rationale: str
    severity: str = "review"  # always 'review' — signals, not conclusions


RISK_RULES: dict[str, list[str]] = {
    "contingent_liabilities": ["contingent liabilit", "guarantee given", "claims not acknowledged"],
    "related_party": ["related party", "related-party", "key managerial personnel"],
    "auditor_qualification": ["qualified opinion", "adverse opinion", "disclaimer of opinion",
                               "emphasis of matter", "material uncertainty"],
    "going_concern": ["going concern"],
    "litigation": ["litigation", "pending legal", "writ petition", "arbitration"],
    "impairment": ["impairment", "goodwill written", "write-down", "write down"],
    "debt_liquidity": ["debt maturit", "refinanc", "liquidity risk", "breach of covenant",
                        "default on"],
    "provisions": ["provision for doubtful", "expected credit loss"],
    "accounting_change": ["change in accounting policy", "restatement", "prior period error"],
    "working_capital": ["increase in receivables", "stretched payables", "inventory build"],
}


def _snippet(text: str, idx: int, term_len: int, width: int = 120) -> str:
    start = max(0, idx - width // 2)
    end = min(len(text), idx + term_len + width // 2)
    return text[start:end].strip()


def scan_text(text: str) -> list[RiskFlag]:
    """Scan text for disclosure signals using transparent keyword rules."""
    flags: list[RiskFlag] = []
    low = text.lower()
    for category, terms in RISK_RULES.items():
        for term in terms:
            for m in re.finditer(re.escape(term), low):
                flags.append(
                    RiskFlag(
                        category=category,
                        matched_term=term,
                        snippet=_snippet(text, m.start(), len(term)),
                        rationale=(
                            f"Matched disclosure keyword '{term}'. This is a signal to "
                            f"review the '{category}' disclosure in context — not a conclusion."
                        ),
                    )
                )
                break  # one flag per term is enough to prompt review
    return flags
