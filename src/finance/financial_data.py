"""Structured storage model for extracted financial facts.

Facts are stored with full provenance and an explicit verification state.
Missing data is represented as ``None`` with status NOT_AVAILABLE — never zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.finance.metrics import FinancialInput, ValueKind


@dataclass
class FinancialFact:
    company_name: str
    financial_year: str
    metric_name: str  # line-item name, e.g. "revenue_from_operations"
    value: Optional[float]
    currency: Optional[str] = None
    units: Optional[str] = None  # scale, e.g. "INR crore"
    basis: str = "unknown"  # standalone | consolidated | unknown
    source_document_id: Optional[str] = None
    source_page: Optional[int] = None
    source_table: Optional[str] = None
    source_note: Optional[str] = None
    extraction_method: str = "manual"  # manual | table_rule | llm_assisted
    verification_status: str = "not_verified"
    kind: ValueKind = ValueKind.REPORTED

    @property
    def available(self) -> bool:
        return self.value is not None

    def to_input(self) -> FinancialInput:
        """Adapt a stored fact to a calculation-engine input."""
        return FinancialInput(
            name=self.metric_name,
            value=self.value,
            currency=self.currency,
            units=self.units,
            period=self.financial_year,
            basis=self.basis,
            kind=self.kind,
            source_document_id=self.source_document_id,
            source_page=self.source_page,
            source_note=self.source_note,
            verification_status=self.verification_status,
        )


class FinancialFactSet:
    """A keyed collection of facts for one company across years."""

    def __init__(self) -> None:
        self._facts: dict[tuple[str, str, str, str], FinancialFact] = {}

    def add(self, fact: FinancialFact) -> None:
        key = (fact.company_name.lower(), fact.financial_year, fact.metric_name, fact.basis)
        self._facts[key] = fact

    def get(
        self, company: str, fy: str, metric: str, basis: str = "consolidated"
    ) -> Optional[FinancialFact]:
        return self._facts.get((company.lower(), fy, metric, basis))

    def years(self, company: str) -> list[str]:
        ys = {k[1] for k in self._facts if k[0] == company.lower()}
        return sorted(ys)

    def all(self) -> list[FinancialFact]:
        return list(self._facts.values())
