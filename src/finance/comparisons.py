"""Cross-year and peer comparison helpers.

These functions never invent data for missing years; gaps are reported
explicitly. Peer comparisons warn when companies use different reporting
bases so the user is not misled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.finance.financial_data import FinancialFactSet
from src.finance.metrics import compute, MetricResult


@dataclass
class YearPoint:
    financial_year: str
    value: Optional[float]
    available: bool
    source_document_id: Optional[str] = None


@dataclass
class TrendSeries:
    company_name: str
    metric_name: str
    basis: str
    points: list[YearPoint]
    missing_years: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_trend(
    facts: FinancialFactSet,
    company: str,
    metric_name: str,
    years: list[str],
    basis: str = "consolidated",
) -> TrendSeries:
    """Build a per-year series for a reported line item, flagging gaps."""
    points: list[YearPoint] = []
    missing: list[str] = []
    for fy in years:
        fact = facts.get(company, fy, metric_name, basis)
        if fact and fact.available:
            points.append(YearPoint(fy, fact.value, True, fact.source_document_id))
        else:
            points.append(YearPoint(fy, None, False))
            missing.append(fy)
    warnings = []
    if missing:
        warnings.append(f"No {basis} '{metric_name}' data for: {', '.join(missing)} (not inferred).")
    return TrendSeries(company, metric_name, basis, points, missing, warnings)


@dataclass
class PeerRow:
    company_name: str
    basis: str
    value: Optional[float]
    available: bool


@dataclass
class PeerComparison:
    metric_name: str
    financial_year: str
    rows: list[PeerRow]
    warnings: list[str] = field(default_factory=list)


def compare_peers(
    facts: FinancialFactSet,
    companies: list[str],
    metric_name: str,
    financial_year: str,
    bases: Optional[dict[str, str]] = None,
) -> PeerComparison:
    """Side-by-side peer comparison for a single metric and year.

    ``bases`` maps company -> reporting basis. A mix of bases raises a warning.
    """
    bases = bases or {}
    rows: list[PeerRow] = []
    seen_bases: set[str] = set()
    for c in companies:
        basis = bases.get(c, "consolidated")
        seen_bases.add(basis)
        fact = facts.get(c, financial_year, metric_name, basis)
        if fact and fact.available:
            rows.append(PeerRow(c, basis, fact.value, True))
        else:
            rows.append(PeerRow(c, basis, None, False))
    warnings: list[str] = []
    if len(seen_bases) > 1:
        warnings.append(
            "Peers use different reporting bases "
            f"({', '.join(sorted(seen_bases))}); figures may not be directly comparable."
        )
    unavailable = [r.company_name for r in rows if not r.available]
    if unavailable:
        warnings.append(f"No data for: {', '.join(unavailable)} ({metric_name} {financial_year}).")
    return PeerComparison(metric_name, financial_year, rows, warnings)


def explain_change(
    facts: FinancialFactSet,
    company: str,
    metric_key: str,
    current_fy: str,
    previous_fy: str,
    input_mapping: dict[str, tuple[str, str]],
    basis: str = "consolidated",
) -> dict:
    """Compute a metric for two years and report the numerical change only.

    ``input_mapping`` maps a metric input slot -> (fact_metric_name, which_year)
    where which_year is 'current' or 'previous'. Returns the two results and the
    delta; narrative explanation is retrieved separately (never invented here).
    """
    def _inputs_for(fy: str) -> dict:
        kwargs = {}
        for slot, (fact_name, year_sel) in input_mapping.items():
            target_fy = current_fy if year_sel == "current" else previous_fy
            fact = facts.get(company, target_fy, fact_name, basis)
            kwargs[slot] = fact.to_input() if fact else None
        return kwargs

    # For a simple ratio metric both inputs share the year; for growth they differ.
    cur = compute(metric_key, **{k: v for k, v in _inputs_for(current_fy).items() if v is not None}) \
        if all(v is not None for v in _inputs_for(current_fy).values()) else None
    prev = compute(metric_key, **{k: v for k, v in _inputs_for(previous_fy).items() if v is not None}) \
        if all(v is not None for v in _inputs_for(previous_fy).values()) else None

    delta = None
    if cur and prev and cur.computed and prev.computed and cur.value is not None and prev.value is not None:
        delta = cur.value - prev.value
    return {
        "metric": metric_key,
        "current": cur.as_dict() if cur else None,
        "previous": prev.as_dict() if prev else None,
        "delta": delta,
        "note": (
            "Delta is a numerical observation only. Management's stated reasons "
            "must be retrieved from the reports and cited separately; causality "
            "is never inferred from the number alone."
        ),
    }
