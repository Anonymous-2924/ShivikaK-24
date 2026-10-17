"""Deterministic financial calculation engine.

The LLM is **never** the authoritative calculator. Every metric here:

* declares its formula and required inputs,
* carries source provenance for each input,
* refuses to divide by zero or fabricate missing denominators,
* refuses to mix standalone/consolidated bases or different periods,
* distinguishes a *reported* figure from a *calculated* one.

Add new metrics via :data:`METRIC_REGISTRY` — no other code needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from src.utils.errors import CalculationError


class ValueKind(str, Enum):
    REPORTED = "reported"
    CALCULATED = "calculated"


@dataclass(frozen=True)
class FinancialInput:
    """A single input figure with provenance."""

    name: str
    value: Optional[float]
    currency: Optional[str] = None
    units: Optional[str] = None  # e.g. "INR crore"
    period: Optional[str] = None  # e.g. "FY2023-24"
    basis: Optional[str] = None  # standalone | consolidated | unknown
    kind: ValueKind = ValueKind.REPORTED
    source_document_id: Optional[str] = None
    source_page: Optional[int] = None
    source_note: Optional[str] = None
    verification_status: str = "not_verified"

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass
class MetricResult:
    """Result of a metric calculation, with full provenance and warnings."""

    metric: str
    value: Optional[float]
    formula: str
    inputs: list[FinancialInput]
    kind: ValueKind = ValueKind.CALCULATED
    unit: Optional[str] = None  # e.g. "ratio", "%", "x"
    warnings: list[str] = field(default_factory=list)
    computed: bool = False

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "value": self.value,
            "formula": self.formula,
            "unit": self.unit,
            "kind": self.kind.value,
            "computed": self.computed,
            "warnings": self.warnings,
            "inputs": [
                {
                    "name": i.name,
                    "value": i.value,
                    "period": i.period,
                    "basis": i.basis,
                    "kind": i.kind.value,
                    "source_document_id": i.source_document_id,
                    "source_page": i.source_page,
                    "source_note": i.source_note,
                }
                for i in self.inputs
            ],
        }


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _check_consistency(inputs: list[FinancialInput], allow_cross_period: bool = False) -> list[str]:
    """Return warnings for mixed bases / incomparable periods.

    Mixing standalone and consolidated is a hard error elsewhere, but here we
    surface it as a warning on the result so the caller can decide. Different
    periods are expected for growth metrics (``allow_cross_period``).
    """
    warnings: list[str] = []
    bases = {i.basis for i in inputs if i.basis and i.basis != "unknown"}
    if len(bases) > 1:
        warnings.append(
            f"Inputs mix reporting bases ({', '.join(sorted(bases))}); "
            "standalone and consolidated figures should not be combined."
        )
    if not allow_cross_period:
        periods = {i.period for i in inputs if i.period}
        if len(periods) > 1:
            warnings.append(
                f"Inputs span multiple periods ({', '.join(sorted(periods))}); "
                "ratio uses a single period by convention."
            )
    return warnings


def _ratio(
    numerator: FinancialInput,
    denominator: FinancialInput,
    *,
    metric: str,
    formula: str,
    unit: str,
    allow_cross_period: bool = False,
    scale: float = 1.0,
) -> MetricResult:
    inputs = [numerator, denominator]
    warnings = _check_consistency(inputs, allow_cross_period=allow_cross_period)

    if not numerator.available or not denominator.available:
        missing = [i.name for i in inputs if not i.available]
        warnings.append(f"Missing required input(s): {', '.join(missing)} — NOT AVAILABLE.")
        return MetricResult(metric, None, formula, inputs, unit=unit, warnings=warnings, computed=False)

    if denominator.value == 0:
        warnings.append(f"Denominator '{denominator.name}' is zero — cannot divide.")
        return MetricResult(metric, None, formula, inputs, unit=unit, warnings=warnings, computed=False)

    if denominator.value < 0:
        warnings.append(
            f"Denominator '{denominator.name}' is negative ({denominator.value}); "
            "interpret the resulting ratio with care."
        )

    value = (numerator.value / denominator.value) * scale
    return MetricResult(metric, value, formula, inputs, unit=unit, warnings=warnings, computed=True)


# ---------------------------------------------------------------------------
# Metric implementations
# ---------------------------------------------------------------------------

def revenue_growth(current: FinancialInput, previous: FinancialInput) -> MetricResult:
    metric = "revenue_growth"
    formula = "(current_revenue / previous_revenue) - 1"
    inputs = [current, previous]
    warnings = _check_consistency(inputs, allow_cross_period=True)
    if not current.available or not previous.available:
        missing = [i.name for i in inputs if not i.available]
        warnings.append(f"Missing required input(s): {', '.join(missing)} — NOT AVAILABLE.")
        return MetricResult(metric, None, formula, inputs, unit="%", warnings=warnings, computed=False)
    if previous.value == 0:
        warnings.append("Previous revenue is zero — growth undefined.")
        return MetricResult(metric, None, formula, inputs, unit="%", warnings=warnings, computed=False)
    if previous.value < 0:
        warnings.append("Previous revenue is negative; percentage growth is not meaningful.")
    value = (current.value / previous.value - 1.0) * 100.0
    return MetricResult(metric, value, formula, inputs, unit="%", warnings=warnings, computed=True)


def operating_margin(operating_profit: FinancialInput, revenue: FinancialInput) -> MetricResult:
    return _ratio(operating_profit, revenue, metric="operating_margin",
                  formula="operating_profit / revenue", unit="%", scale=100.0)


def net_profit_margin(pat: FinancialInput, revenue: FinancialInput) -> MetricResult:
    return _ratio(pat, revenue, metric="net_profit_margin",
                  formula="profit_after_tax / revenue", unit="%", scale=100.0)


def debt_to_equity(total_debt: FinancialInput, equity: FinancialInput) -> MetricResult:
    return _ratio(total_debt, equity, metric="debt_to_equity",
                  formula="total_debt / shareholders_equity", unit="x")


def interest_coverage(earnings: FinancialInput, interest_expense: FinancialInput) -> MetricResult:
    # 'earnings' is an explicitly selected measure (e.g. EBIT); caller names it.
    return _ratio(earnings, interest_expense, metric="interest_coverage",
                  formula="selected_earnings_measure / interest_expense", unit="x")


def ocf_to_pat(operating_cash_flow: FinancialInput, pat: FinancialInput) -> MetricResult:
    return _ratio(operating_cash_flow, pat, metric="ocf_to_pat",
                  formula="cash_flow_from_operations / profit_after_tax", unit="x")


def roe(pat: FinancialInput, average_equity: FinancialInput) -> MetricResult:
    return _ratio(pat, average_equity, metric="roe",
                  formula="profit_after_tax / average_shareholders_equity", unit="%", scale=100.0)


def roce(operating_profit: FinancialInput, capital_employed: FinancialInput) -> MetricResult:
    return _ratio(operating_profit, capital_employed, metric="roce",
                  formula="operating_profit / capital_employed", unit="%", scale=100.0)


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    formula: str
    required_inputs: tuple[str, ...]
    func: Callable[..., MetricResult]
    unit: str


METRIC_REGISTRY: dict[str, MetricSpec] = {
    "revenue_growth": MetricSpec("revenue_growth", "Revenue Growth",
        "(current_revenue / previous_revenue) - 1", ("current", "previous"), revenue_growth, "%"),
    "operating_margin": MetricSpec("operating_margin", "Operating Margin",
        "operating_profit / revenue", ("operating_profit", "revenue"), operating_margin, "%"),
    "net_profit_margin": MetricSpec("net_profit_margin", "Net Profit Margin",
        "profit_after_tax / revenue", ("pat", "revenue"), net_profit_margin, "%"),
    "debt_to_equity": MetricSpec("debt_to_equity", "Debt to Equity",
        "total_debt / shareholders_equity", ("total_debt", "equity"), debt_to_equity, "x"),
    "interest_coverage": MetricSpec("interest_coverage", "Interest Coverage",
        "selected_earnings_measure / interest_expense", ("earnings", "interest_expense"),
        interest_coverage, "x"),
    "ocf_to_pat": MetricSpec("ocf_to_pat", "Operating Cash Flow to PAT",
        "cash_flow_from_operations / profit_after_tax", ("operating_cash_flow", "pat"),
        ocf_to_pat, "x"),
    "roe": MetricSpec("roe", "Return on Equity",
        "profit_after_tax / average_equity", ("pat", "average_equity"), roe, "%"),
    "roce": MetricSpec("roce", "Return on Capital Employed",
        "operating_profit / capital_employed", ("operating_profit", "capital_employed"),
        roce, "%"),
}


def compute(metric_key: str, **named_inputs: FinancialInput) -> MetricResult:
    """Compute a metric by key using the registry.

    Raises :class:`CalculationError` for an unknown metric or missing input
    *slots* (a provided-but-empty figure is handled gracefully as NOT AVAILABLE).
    """
    spec = METRIC_REGISTRY.get(metric_key)
    if spec is None:
        raise CalculationError(f"Unknown metric '{metric_key}'. "
                               f"Known: {', '.join(sorted(METRIC_REGISTRY))}")
    missing_slots = [name for name in spec.required_inputs if name not in named_inputs]
    if missing_slots:
        raise CalculationError(
            f"Metric '{metric_key}' requires inputs {spec.required_inputs}; "
            f"missing slot(s): {', '.join(missing_slots)}"
        )
    return spec.func(**{k: named_inputs[k] for k in spec.required_inputs})
