"""Query classification + decomposition.

Deterministic classifier + dispatcher, NOT an agent (brief rule — faster,
cheaper, debuggable). Most real questions touch more than one of the
three retrieval modes, so the router does not pick exactly one category:
it decomposes a question into the set of categories it plausibly needs,
and ``src/retrieve/combine.py`` recombines whatever the dispatchers
return.

This first pass is regex + keyword heuristics, as the brief asks for.
It is not NLU: entity-name extraction in particular (``entity_hints``) is
a capitalised-phrase heuristic, not NER. Phase 6's eval harness is where
this gets measured against real questions; improve the heuristics there
if precision is poor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SEMANTIC = "semantic"
STRUCTURAL = "structural"
QUANTITATIVE = "quantitative"

_STRUCTURAL_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bdepends? on\b", r"\bdepend(?:ency|encies)\b",
        r"\bsupplied by\b", r"\bsupplier(?:s)? of\b", r"\bwho supplies\b",
        r"\breachable\b", r"\bpath(?:s)?\b", r"\bupstream\b", r"\bdownstream\b",
        r"\bexpos(?:ed|ure)\b", r"\baffect(?:s|ed|ing)?\b",
        r"\bconnected to\b", r"\btier[- ]?2\b", r"\btier[- ]?1\b",
        r"\bprobable (?:tier|supplier)\b", r"\bmanufactured at\b",
        r"\bships? via\b", r"\broute(?:s)?\b", r"\bgoes? down\b",
        r"\bdisrupt(?:ed|ion)\b", r"\bwhich skus?\b", r"\bwhat skus?\b",
    ]
]

_QUANTITATIVE_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\brevenue\b", r"\bcost(?:s)?\b", r"\bprice(?:s|d)?\b", r"\$",
        r"\bbuffer\s*days?\b", r"\blead\s*time\b", r"\bhow many days\b",
        r"\bhow much\b", r"\bvolume(?:s)?\b", r"\bunits?\b",
        r"\bdollar(?:s)?\b", r"\bfinancial(?:s)?\b", r"\bspend\b",
        r"\bat risk\b", r"\binventory\b", r"\bcapacity\b",
    ]
]

_SEMANTIC_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bsaid\b", r"\bsays?\b", r"\bmention(?:ed|s)?\b",
        r"\baccording to\b", r"\baudit\b", r"\breport(?:ed)?\b",
        r"\bfinding(?:s)?\b", r"\bfeedback\b", r"\bnews\b", r"\bletter\b",
        r"\bemail\b", r"\bdescribe(?:d)?\b", r"\bwhy\b", r"\bchemical\b",
        r"\bsafety\b", r"\bcomplain(?:t|ts|ed)?\b", r"\bviolation(?:s)?\b",
    ]
]

# Capitalised multi-word (or single, non-leading-word) spans — a cheap
# proxy for proper nouns ("ACME Textiles", "Dhaka", "Plant X").
_PROPER_NOUN = re.compile(r"\b([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*)\b")
_QUESTION_LEADERS = {
    "What", "Which", "Who", "How", "Why", "When", "Where", "Is", "Are",
    "Does", "Do", "Did", "Can", "Could", "Would", "Should", "If",
}
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


@dataclass
class QueryPlan:
    """What the router decided about one question."""
    question: str
    categories: set[str]
    entity_hints: list[str] = field(default_factory=list)
    as_of: str | None = None


def classify_query(question: str, *, as_of: str | None = None) -> QueryPlan:
    """Classify + decompose a question into the retrieval categories it
    plausibly needs, plus any entity-name hints found in the text.

    ``as_of`` passed explicitly (e.g. from a CLI flag) always wins over
    one embedded in the question text.
    """
    categories: set[str] = set()
    if any(p.search(question) for p in _STRUCTURAL_PATTERNS):
        categories.add(STRUCTURAL)
    if any(p.search(question) for p in _QUANTITATIVE_PATTERNS):
        categories.add(QUANTITATIVE)
    if any(p.search(question) for p in _SEMANTIC_PATTERNS):
        categories.add(SEMANTIC)

    # Exposure-tracing shape (brief's core use case): an event/disruption
    # mentioned alongside an impact word pulls in all three modes —
    # structural to trace the path, quantitative for revenue/buffer,
    # semantic for supporting narrative evidence (e.g. the event itself).
    if STRUCTURAL in categories and QUANTITATIVE in categories:
        categories.add(SEMANTIC)

    # A question that matched nothing is most likely a plain narrative
    # lookup — default to semantic rather than return an empty plan.
    if not categories:
        categories.add(SEMANTIC)

    resolved_as_of = as_of
    if resolved_as_of is None:
        m = _DATE_RE.search(question)
        if m:
            resolved_as_of = m.group(1)

    return QueryPlan(
        question=question,
        categories=categories,
        entity_hints=_extract_entity_hints(question),
        as_of=resolved_as_of,
    )


def _extract_entity_hints(question: str) -> list[str]:
    hints: list[str] = []
    for m in _PROPER_NOUN.finditer(question):
        span = m.group(1).strip()
        words = span.split()
        # Drop a leading question-word that only looks capitalised because
        # it starts the sentence (e.g. "What" in "What depends on ACME?").
        if words and words[0] in _QUESTION_LEADERS:
            words = words[1:]
        span = " ".join(words)
        if len(span) >= 2 and span not in hints:
            hints.append(span)
    return hints
