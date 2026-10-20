"""Top-level ER driver — walks the entity population and populates the
merge store + review queue.

Strategy:
  * Block candidates by (country_code, entity type) — comparing every
    pair is O(n²) and 700 suppliers alone would be 245k pairs. Blocking
    cuts it by orders of magnitude without losing recall.
  * For each candidate pair in a block, score, classify, and route.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.resolve.merges import Merge, MergeStore
from src.resolve.similarity import AUTO_MERGE, REVIEW, EntityRecord, classify, score


@dataclass
class ResolveStats:
    pairs_considered: int = 0
    auto_merged: int = 0
    sent_to_review: int = 0
    auto_rejected: int = 0


def resolve_population(entities: list[EntityRecord], store: MergeStore,
                        *, auto_merge_threshold: float = 0.92,
                        review_threshold: float = 0.78,
                        log_fn=print) -> ResolveStats:
    stats = ResolveStats()

    # Block by (type, country_code). Entities without a country go into a
    # separate "unknown-country" block of the same type.
    blocks: dict[tuple[str, str], list[EntityRecord]] = defaultdict(list)
    for e in entities:
        blocks[(e.type, e.country_code or "?")].append(e)

    log_fn(f"[resolve] {len(entities)} entities into {len(blocks)} blocks")

    for (_etype, country), bucket in blocks.items():
        if len(bucket) < 2:
            continue
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                stats.pairs_considered += 1
                ps = score(a, b)
                verdict = classify(ps,
                                    auto_merge_threshold=auto_merge_threshold,
                                    review_threshold=review_threshold)
                if verdict == AUTO_MERGE:
                    canonical, source = _pick_canonical(a, b)
                    store.record_merge(Merge(
                        source_id=source.id, canonical_id=canonical.id,
                        score=ps.combined,
                        evidence={
                            "string": ps.string, "address": ps.address,
                            "shared_tax_id": ps.shared_tax_id,
                            "shared_country": ps.shared_country,
                            "shared_customer": ps.shared_customer,
                            "shared_route": ps.shared_route,
                            "pair_names": [a.name, b.name],
                        },
                        created_by="auto",
                    ))
                    stats.auto_merged += 1
                elif verdict == REVIEW:
                    store.enqueue_review(
                        left_id=a.id, right_id=b.id, score=ps.combined,
                        evidence={
                            "pair_names": [a.name, b.name],
                            "pair_types": [a.type, b.type],
                            "country": country,
                            "string": ps.string, "address": ps.address,
                            "shared_tax_id": ps.shared_tax_id,
                            "shared_country": ps.shared_country,
                        },
                    )
                    stats.sent_to_review += 1
                else:
                    stats.auto_rejected += 1
    log_fn(f"[resolve] considered {stats.pairs_considered} pairs: "
           f"auto-merge {stats.auto_merged}, "
           f"review {stats.sent_to_review}, "
           f"reject {stats.auto_rejected}")
    return stats


def _pick_canonical(a: EntityRecord, b: EntityRecord):
    """Keep the longer/more-complete name as the canonical. On ties, the
    lexicographically smaller id wins — deterministic across runs."""
    if (a.tax_id and not b.tax_id):
        return a, b
    if (b.tax_id and not a.tax_id):
        return b, a
    if len(a.name) != len(b.name):
        return (a, b) if len(a.name) > len(b.name) else (b, a)
    return (a, b) if a.id < b.id else (b, a)
