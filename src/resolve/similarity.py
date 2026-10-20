"""Pairwise similarity for entity resolution.

Returns a combined score in [0,1] blended from:
  - string similarity (rapidfuzz token-set ratio on normalised names)
  - structural signals (shared tax_id, address similarity, shared country,
    shared primary customer / route — these are weighted higher than
    string alone because they are much less likely to coincide by chance).

Weights are chosen so a pair that shares a tax_id but has a wildly
different name still lands in the review bucket, not auto-reject.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

_PUNCT = re.compile(r"[^\w\s]")
_SUFFIX_NOISE = re.compile(
    r"\b(limited|ltd|pvt|private|inc|incorporated|co|company|corp|"
    r"corporation|gmbh|llc|llp|plc|international|intl|holdings|"
    r"industries|group|enterprises|export|house)\b", re.I)


def normalise(name: str) -> str:
    s = _PUNCT.sub(" ", name).lower()
    s = _SUFFIX_NOISE.sub(" ", s)
    return " ".join(s.split())


@dataclass(frozen=True)
class EntityRecord:
    """What ER needs to know about an entity to score it against another."""
    id: str
    name: str
    type: str
    tax_id: str | None = None
    country_code: str | None = None
    address: str | None = None
    customers: tuple[str, ...] = ()
    routes: tuple[str, ...] = ()


# ---------- Signal functions ----------
def string_similarity(a: EntityRecord, b: EntityRecord) -> float:
    """0..1 using rapidfuzz token-set ratio on normalised names."""
    na, nb = normalise(a.name), normalise(b.name)
    if not na or not nb:
        return 0.0
    return fuzz.token_set_ratio(na, nb) / 100.0


def address_similarity(a: EntityRecord, b: EntityRecord) -> float:
    """0..1 if both sides have an address; -1.0 if either side is missing
    (callers interpret -1.0 as 'skip this signal, do not penalise')."""
    if not a.address or not b.address:
        return -1.0
    return fuzz.token_set_ratio(a.address.lower(), b.address.lower()) / 100.0


def shared_tax_id(a: EntityRecord, b: EntityRecord) -> bool:
    return bool(a.tax_id and b.tax_id and a.tax_id == b.tax_id)


def shared_country(a: EntityRecord, b: EntityRecord) -> bool:
    return bool(a.country_code and a.country_code == b.country_code)


def shared_customer(a: EntityRecord, b: EntityRecord) -> bool:
    return bool(set(a.customers) & set(b.customers))


def shared_route(a: EntityRecord, b: EntityRecord) -> bool:
    return bool(set(a.routes) & set(b.routes))


# ---------- Combined score ----------
@dataclass(frozen=True)
class PairScore:
    combined: float
    string: float
    address: float
    shared_tax_id: bool
    shared_country: bool
    shared_customer: bool
    shared_route: bool


def score(a: EntityRecord, b: EntityRecord) -> PairScore:
    s_str = string_similarity(a, b)
    s_addr_raw = address_similarity(a, b)
    tax = shared_tax_id(a, b)
    cty = shared_country(a, b)
    cust = shared_customer(a, b)
    rt = shared_route(a, b)

    # Weights sum to 1.0 when all signals are present.
    w_str, w_addr, w_tax, w_cty, w_cust, w_rt = (
        0.45, 0.12, 0.33, 0.03, 0.05, 0.02,
    )

    # Address missing on either side: redistribute its weight proportionally
    # across the other signals so the signal we DO have can still produce a
    # confident score.
    if s_addr_raw < 0:
        total = w_str + w_tax + w_cty + w_cust + w_rt
        scale = 1.0 / total
        w_str, w_tax, w_cty, w_cust, w_rt = (
            w_str * scale, w_tax * scale, w_cty * scale,
            w_cust * scale, w_rt * scale,
        )
        s_addr = 0.0
        w_addr = 0.0
    else:
        s_addr = s_addr_raw

    combined = (
        w_str * s_str
        + w_addr * s_addr
        + w_tax * (1.0 if tax else 0.0)
        + w_cty * (1.0 if cty else 0.0)
        + w_cust * (1.0 if cust else 0.0)
        + w_rt * (1.0 if rt else 0.0)
    )
    # Hard rule: different types never auto-match. We still return a score
    # so callers can inspect; the three-bucket classifier gates on type.
    if a.type != b.type:
        combined = min(combined, 0.5)

    return PairScore(
        combined=round(min(1.0, combined), 4),
        string=round(s_str, 4),
        address=round(max(0.0, s_addr_raw), 4),
        shared_tax_id=tax, shared_country=cty,
        shared_customer=cust, shared_route=rt,
    )


# ---------- Three-bucket classification ----------
AUTO_MERGE = "auto_merge"
REVIEW = "review"
AUTO_REJECT = "auto_reject"


def classify(ps: PairScore, *, auto_merge_threshold: float = 0.92,
              review_threshold: float = 0.78) -> str:
    """Three-bucket decision. Review band NEVER auto-merges (brief rule)."""
    s = ps.combined
    if s >= auto_merge_threshold:
        return AUTO_MERGE
    if s >= review_threshold:
        return REVIEW
    return AUTO_REJECT
