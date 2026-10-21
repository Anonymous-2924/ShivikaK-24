"""Metric calculators on synthetic input — no corpus, no services."""
from __future__ import annotations

import pytest

from eval.metrics import (
    cost_usd,
    extract_entity_mentions,
    hallucination_rate,
    latency_stats,
    path_correctness,
    retrieval_precision,
)


def test_retrieval_precision_exact_match():
    assert retrieval_precision(["a.pdf", "b.pdf"], ["a.pdf", "b.pdf", "c.pdf"]) == 1.0


def test_retrieval_precision_partial_match():
    assert retrieval_precision(["a.pdf", "x.pdf"], ["a.pdf"]) == 0.5


def test_retrieval_precision_nothing_returned_is_zero_not_error():
    assert retrieval_precision([], ["a.pdf"]) == 0.0


def test_retrieval_precision_glob_expected_doc_id():
    assert retrieval_precision(
        ["daily_demand_2026-01.csv"], ["daily_demand_*.csv"]
    ) == 1.0


def test_path_correctness_jaccard():
    assert path_correctness(["A", "B", "C"], ["A", "B", "D"]) == 2 / 4


def test_path_correctness_perfect_match():
    assert path_correctness(["A", "B"], ["A", "B"]) == 1.0


def test_path_correctness_none_expected_returns_none():
    assert path_correctness(["A"], None) is None


def test_path_correctness_both_empty_is_perfect():
    assert path_correctness([], []) == 1.0


def test_path_correctness_returned_empty_expected_nonempty_is_zero():
    assert path_correctness([], ["A"]) == 0.0


def test_hallucination_rate_all_real():
    assert hallucination_rate(["SKU-1", "SKU-2"], {"SKU-1", "SKU-2"}) == 0.0


def test_hallucination_rate_some_fake():
    assert hallucination_rate(["SKU-1", "SKU-FAKE"], {"SKU-1"}) == 0.5


def test_hallucination_rate_no_mentions_is_none():
    assert hallucination_rate([], {"SKU-1"}) is None


def test_extract_entity_mentions_finds_id_shaped_tokens():
    text = "SKU-100 depends on SUP-T1-0001 via CMP-FAB-0003."
    mentions = extract_entity_mentions(text)
    assert set(mentions) == {"SKU-100", "SUP-T1-0001", "CMP-FAB-0003"}


def test_extract_entity_mentions_empty_text():
    assert extract_entity_mentions("") == []


def test_extract_entity_mentions_plain_prose_finds_nothing():
    assert extract_entity_mentions("No evidence found.") == []


def test_latency_stats_basic():
    stats = latency_stats([10, 20, 30, 40, 50])
    assert stats.n == 5
    assert stats.p50_ms == 30
    assert stats.p95_ms == pytest.approx(48.0)


def test_latency_stats_empty():
    stats = latency_stats([])
    assert stats.n == 0
    assert stats.p50_ms == 0.0
    assert stats.p95_ms == 0.0


def test_cost_usd_free_model_is_zero():
    assert cost_usd(1000, 500, "gpt-oss:20b") == 0.0


def test_cost_usd_unknown_model_defaults_to_zero_not_a_guess():
    assert cost_usd(1000, 500, "some-unpublished-model") == 0.0
