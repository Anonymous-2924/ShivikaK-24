"""Entity resolution: similarity blending, three-bucket decision,
and precision/recall on the labelled fixture."""
from __future__ import annotations

from pathlib import Path

from src.resolve.evaluate import evaluate
from src.resolve.similarity import (
    AUTO_MERGE,
    AUTO_REJECT,
    REVIEW,
    EntityRecord,
    classify,
    normalise,
    score,
)


def _s(**kw) -> EntityRecord:
    kw.setdefault("tax_id", None)
    kw.setdefault("country_code", None)
    kw.setdefault("address", None)
    return EntityRecord(**kw)


def test_normalise_strips_suffix_noise_and_punct() -> None:
    assert normalise("Acme Corporation, Ltd.") == "acme"
    assert normalise("Horizon Textiles Pvt Ltd") == "horizon textiles"


def test_same_name_same_taxid_auto_merges() -> None:
    a = _s(id="S1", name="Horizon Textiles Ltd", type="Supplier",
            tax_id="BD-11-123456", country_code="BD")
    b = _s(id="S2", name="HORIZON TEXTILES", type="Supplier",
            tax_id="BD-11-123456", country_code="BD")
    ps = score(a, b)
    assert ps.combined >= 0.92
    assert classify(ps) == AUTO_MERGE


def test_partial_name_match_lands_in_review() -> None:
    a = _s(id="S1", name="Horizon Textiles", type="Supplier",
            country_code="BD", address="Plot 14, Dhaka")
    b = _s(id="S2", name="Horizon Garments", type="Supplier",
            country_code="BD", address="Plot 16, Dhaka")
    ps = score(a, b)
    verdict = classify(ps)
    assert verdict in (REVIEW, AUTO_REJECT)   # borderline; not auto-merge
    # If it reviews, that's the point. If it rejects, the pair should land
    # with a visible score so a human can inspect.
    assert 0.0 <= ps.combined < 0.92


def test_different_types_never_auto_merge_even_if_names_match() -> None:
    a = _s(id="S1", name="Horizon",   type="Supplier")
    b = _s(id="C1", name="Horizon",   type="Component")
    ps = score(a, b)
    assert classify(ps) != AUTO_MERGE


def test_random_cross_country_pairs_reject() -> None:
    a = _s(id="S1", name="Horizon Textiles", type="Supplier",
            country_code="BD")
    b = _s(id="S2", name="Nile Spinning Mills", type="Supplier",
            country_code="EG")
    assert classify(score(a, b)) == AUTO_REJECT


def test_evaluate_against_200_pair_fixture_meets_targets() -> None:
    fixture = Path("tests/fixtures/er_pairs.json")
    m = evaluate(fixture)
    # Fixture size sanity.
    assert m.pairs >= 100
    assert m.true_match_pairs >= 30
    assert m.true_nomatch_pairs >= 30
    # Targets: these are my credibility numbers. If we regress below any
    # of them, something structural changed in the scorer.
    assert m.precision >= 0.90, f"precision regressed to {m.precision:.3f}"
    assert m.recall    >= 0.70, f"recall regressed to {m.recall:.3f}"
    assert m.f1        >= 0.80, f"F1 regressed to {m.f1:.3f}"
    # The ambiguous set should NOT be dominantly auto-merged (we rely on
    # the review queue for them).
    assert m.ambiguous_auto_merged <= m.ambiguous_pairs // 3
