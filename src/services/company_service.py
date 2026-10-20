"""Company exploration + discovery service."""
from __future__ import annotations

from dataclasses import dataclass

from src.ingestion.report_discovery import default_registry
from src.services.context import AppContext


@dataclass
class CompanyCoverage:
    company_name: str
    years: list[str]
    report_count: int


class CompanyService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.registry = default_registry()

    def indexed_companies(self) -> list[CompanyCoverage]:
        docs = self.ctx.metadata_store.list_documents()
        by_company: dict[str, list[dict]] = {}
        for d in docs:
            by_company.setdefault(d["company_name"], []).append(d)
        out = []
        for name, items in sorted(by_company.items()):
            years = sorted({i["financial_year"] for i in items if i.get("financial_year")})
            out.append(CompanyCoverage(name, years, len(items)))
        return out

    def search(self, query: str):
        return self.registry.search_companies(query)

    def coverage_gaps(self, company_name: str, start_year: int, end_year: int) -> list[str]:
        """Return the FY labels in range that are NOT present (never inferred)."""
        present = set()
        for d in self.ctx.metadata_store.list_documents():
            if d["company_name"].lower() == company_name.lower() and d.get("financial_year"):
                present.add(d["financial_year"])
        expected = [f"FY{y}-{str(y+1)[-2:]}" for y in range(start_year, end_year)]
        return [fy for fy in expected if fy not in present]
