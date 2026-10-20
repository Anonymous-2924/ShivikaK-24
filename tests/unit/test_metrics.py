"""Tests for the deterministic financial calculation engine."""
import pytest

from src.finance.metrics import (
    FinancialInput,
    ValueKind,
    compute,
    operating_margin,
    revenue_growth,
    debt_to_equity,
)
from src.utils.errors import CalculationError


def _inp(name, value, **kw):
    return FinancialInput(name=name, value=value, **kw)


def test_revenue_growth_basic():
    r = revenue_growth(_inp("rev", 121, period="FY2024"), _inp("rev", 100, period="FY2023"))
    assert r.computed
    assert r.value == pytest.approx(21.0)
    assert r.unit == "%"
    assert r.kind == ValueKind.CALCULATED


def test_revenue_growth_zero_previous_not_computed():
    r = revenue_growth(_inp("rev", 100), _inp("rev", 0))
    assert not r.computed
    assert r.value is None
    assert any("undefined" in w for w in r.warnings)


def test_operating_margin_percent():
    r = operating_margin(_inp("op", 25), _inp("rev", 100))
    assert r.value == pytest.approx(25.0)


def test_divide_by_zero_is_flagged_not_raised():
    r = operating_margin(_inp("op", 25), _inp("rev", 0))
    assert r.value is None
    assert not r.computed
    assert any("zero" in w.lower() for w in r.warnings)


def test_missing_input_marked_not_available():
    r = operating_margin(_inp("op", None), _inp("rev", 100))
    assert r.value is None
    assert any("NOT AVAILABLE" in w for w in r.warnings)


def test_mixed_basis_warning():
    r = debt_to_equity(
        _inp("debt", 50, basis="standalone"),
        _inp("equity", 100, basis="consolidated"),
    )
    assert r.computed  # still computes
    assert any("reporting bases" in w for w in r.warnings)


def test_registry_compute_and_unknown_metric():
    r = compute("operating_margin", operating_profit=_inp("op", 10), revenue=_inp("rev", 50))
    assert r.value == pytest.approx(20.0)
    with pytest.raises(CalculationError):
        compute("not_a_metric", a=_inp("a", 1))


def test_registry_missing_slot_raises():
    with pytest.raises(CalculationError):
        compute("operating_margin", operating_profit=_inp("op", 10))


def test_result_provenance_preserved():
    r = compute(
        "net_profit_margin",
        pat=_inp("pat", 10, source_document_id="doc1", source_page=142),
        revenue=_inp("rev", 100, source_document_id="doc1", source_page=140),
    )
    d = r.as_dict()
    assert d["inputs"][0]["source_document_id"] == "doc1"
    assert d["inputs"][0]["source_page"] == 142
    assert d["kind"] == "calculated"
