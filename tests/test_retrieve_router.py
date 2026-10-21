"""Classifier correctness for the deterministic query router."""
from __future__ import annotations

from src.retrieve.router import QUANTITATIVE, SEMANTIC, STRUCTURAL, classify_query


def test_semantic_only_for_narrative_question():
    plan = classify_query("What did the audit say about ACME's fire safety?")
    assert plan.categories == {SEMANTIC}


def test_structural_only_for_dependency_question():
    plan = classify_query("What depends on ACME?")
    assert plan.categories == {STRUCTURAL}


def test_exposure_question_pulls_in_all_three():
    plan = classify_query(
        "If the Chittagong plant goes down, which SKUs are exposed and "
        "how much revenue is at risk?"
    )
    assert plan.categories == {SEMANTIC, STRUCTURAL, QUANTITATIVE}


def test_quantitative_keyword_detected():
    plan = classify_query("How many buffer days do we have for SKU A?")
    assert QUANTITATIVE in plan.categories


def test_unmatched_question_defaults_to_semantic():
    plan = classify_query("blah blah nothing matches anything here")
    assert plan.categories == {SEMANTIC}


def test_entity_hints_strip_leading_question_word():
    plan = classify_query("What depends on ACME Textiles?")
    assert "ACME Textiles" in plan.entity_hints
    assert "What" not in plan.entity_hints


def test_as_of_flag_wins_over_date_in_question_text():
    plan = classify_query("revenue at risk as of 2026-01-01", as_of="2026-06-15")
    assert plan.as_of == "2026-06-15"


def test_as_of_extracted_from_question_text_when_not_passed():
    plan = classify_query("what was the buffer on 2025-11-03?")
    assert plan.as_of == "2025-11-03"


def test_no_as_of_when_absent_everywhere():
    plan = classify_query("what depends on ACME?")
    assert plan.as_of is None
