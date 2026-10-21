"""Metric calculators for the Phase 6 eval harness.

Every function here takes plain data (lists/sets of ids, floats) and
returns a plain number — no dependency on a running system, so these
are unit-testable on synthetic input (see tests/test_eval_metrics.py)
independent of whether Qdrant/Neo4j/Ollama are reachable.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Published Ollama Cloud free-tier rate for the models this project
# actually uses (see README's pinned-version table: gpt-oss:20b and
# nemotron-3-ultra are both free-tier). $0 is not a placeholder — it's
# what the project's own locked model choices actually cost. Fill in a
# real published $/1K-token rate here (and re-verify it) before relying
# on this for a paid model; do not guess a number.
MODEL_RATES_USD_PER_1K_TOKENS: dict[str, float] = {
    "gpt-oss:20b": 0.0,
    "nemotron-3-ultra": 0.0,
}

_ID_LIKE = re.compile(
    r"\b(?:SKU|SUP|CMP|PLT|RTE|PORT|GEO|TBL)[A-Z0-9-]{3,}\b"
)


def retrieval_precision(returned_doc_ids: list[str],
                         expected_doc_ids: list[str]) -> float:
    """Fraction of returned sources that are in the expected set.
    Returns 0.0 if nothing was returned (not undefined/NaN — an eval
    report needs a number it can average, and 'returned nothing' is a
    real, scoreable outcome)."""
    if not returned_doc_ids:
        return 0.0
    expected = set(expected_doc_ids)
    hits = sum(1 for d in returned_doc_ids if _doc_id_matches(d, expected))
    return hits / len(returned_doc_ids)


def _doc_id_matches(doc_id: str, expected: set[str]) -> bool:
    """Exact match, or a glob-style expected entry like
    'daily_demand_*.csv' (used for questions whose evidence is spread
    across many dated files)."""
    if doc_id in expected:
        return True
    for exp in expected:
        if "*" in exp:
            pattern = "^" + re.escape(exp).replace(r"\*", ".*") + "$"
            if re.match(pattern, doc_id):
                return True
    return False


def path_correctness(returned_sku_ids: list[str] | set[str],
                      expected_sku_ids: list[str] | set[str] | None) -> float | None:
    """Jaccard similarity of the returned SKU-id set vs the expected one.
    Returns None (not 0.0) when the question has no expected_sku_ids —
    that means the metric doesn't apply to this question, which is a
    different thing from the system getting it wrong."""
    if expected_sku_ids is None:
        return None
    a, b = set(returned_sku_ids), set(expected_sku_ids)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def hallucination_rate(mentioned_entity_ids: list[str],
                        known_entity_ids: set[str]) -> float | None:
    """Fraction of entity-id-shaped mentions in a system's answer that
    don't exist in the real graph/corpus. None if the answer mentioned
    no entity-shaped ids at all (nothing to check, not a perfect score)."""
    if not mentioned_entity_ids:
        return None
    bad = sum(1 for e in mentioned_entity_ids if e not in known_entity_ids)
    return bad / len(mentioned_entity_ids)


def extract_entity_mentions(text: str) -> list[str]:
    """Pull id-shaped tokens (SKU-..., SUP-..., CMP-..., etc.) out of a
    free-text answer, for the hallucination check above."""
    return _ID_LIKE.findall(text or "")


@dataclass(frozen=True)
class LatencyStats:
    p50_ms: float
    p95_ms: float
    n: int


def latency_stats(samples_ms: list[float]) -> LatencyStats:
    if not samples_ms:
        return LatencyStats(p50_ms=0.0, p95_ms=0.0, n=0)
    ordered = sorted(samples_ms)
    return LatencyStats(
        p50_ms=_percentile(ordered, 50), p95_ms=_percentile(ordered, 95),
        n=len(ordered),
    )


def _percentile(ordered: list[float], pct: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return ordered[int(k)]
    frac = k - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def cost_usd(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Token counts x the published rate for ``model``. Returns 0.0 for
    any model not in MODEL_RATES_USD_PER_1K_TOKENS — explicitly 'rate
    unknown, treated as free' rather than silently guessing a number;
    callers that care should check the model is in the table first."""
    rate = MODEL_RATES_USD_PER_1K_TOKENS.get(model, 0.0)
    return round((prompt_tokens + completion_tokens) / 1000.0 * rate, 6)


def estimate_tokens(text: str) -> int:
    """Rough token-count proxy (chars / 4) — NOT a real tokenizer count.
    Only good enough for an order-of-magnitude cost estimate; the
    project's actual models are free-tier so this rarely matters in
    practice (see MODEL_RATES_USD_PER_1K_TOKENS)."""
    return max(1, len(text) // 4)
