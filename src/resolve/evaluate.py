"""Evaluate ER against a labelled pair set — precision / recall / F1.

Loader for tests/fixtures/er_pairs.json. Each entry is:

    {"left": {<EntityRecord dict>},
     "right": {<EntityRecord dict>},
     "label": "match" | "no_match" | "ambiguous"}

The 'ambiguous' label is excluded from the precision/recall calculation —
it is only informational, used to make sure the review queue catches them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.resolve.similarity import AUTO_MERGE, EntityRecord, classify, score


@dataclass
class ERMetrics:
    pairs: int
    true_match_pairs: int
    true_nomatch_pairs: int
    ambiguous_pairs: int
    tp: int
    fp: int
    fn: int
    tn: int
    # ambiguous breakdown — informational
    ambiguous_in_review: int
    ambiguous_auto_merged: int
    ambiguous_auto_rejected: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def load_pairs(path: Path) -> list[dict]:
    doc = json.loads(path.read_text())
    return doc.get("pairs", [])


def evaluate(pairs_path: Path, *, auto_merge_threshold: float = 0.92,
             review_threshold: float = 0.78) -> ERMetrics:
    pairs = load_pairs(pairs_path)
    tp = fp = fn = tn = 0
    amb_rev = amb_merge = amb_rej = 0
    true_m = true_nm = amb = 0
    for p in pairs:
        a = _entity_from(p["left"])
        b = _entity_from(p["right"])
        label = p["label"]
        ps = score(a, b)
        verdict = classify(ps,
                            auto_merge_threshold=auto_merge_threshold,
                            review_threshold=review_threshold)
        predicted_match = (verdict == AUTO_MERGE)
        if label == "match":
            true_m += 1
            if predicted_match:
                tp += 1
            else:
                fn += 1
        elif label == "no_match":
            true_nm += 1
            if predicted_match:
                fp += 1
            else:
                tn += 1
        elif label == "ambiguous":
            amb += 1
            if verdict == "review":
                amb_rev += 1
            elif verdict == AUTO_MERGE:
                amb_merge += 1
            else:
                amb_rej += 1
    return ERMetrics(
        pairs=len(pairs),
        true_match_pairs=true_m, true_nomatch_pairs=true_nm,
        ambiguous_pairs=amb,
        tp=tp, fp=fp, fn=fn, tn=tn,
        ambiguous_in_review=amb_rev,
        ambiguous_auto_merged=amb_merge,
        ambiguous_auto_rejected=amb_rej,
    )


def _entity_from(d: dict) -> EntityRecord:
    return EntityRecord(
        id=d["id"], name=d["name"], type=d["type"],
        tax_id=d.get("tax_id"),
        country_code=d.get("country_code"),
        address=d.get("address"),
        customers=tuple(d.get("customers") or ()),
        routes=tuple(d.get("routes") or ()),
    )
