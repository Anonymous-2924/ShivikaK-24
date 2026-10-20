"""Report discovery registry.

Aggregates company-search and report-discovery providers. Only the manual
provider is registered by default; official-source adapters can be registered
here once implemented against documented, permitted access mechanisms.
"""
from __future__ import annotations

from src.ingestion.source_adapters.base import (
    AnnualReportDiscoveryProvider,
    CompanyMatch,
    CompanySearchProvider,
    ReportListing,
)
from src.ingestion.source_adapters.manual import ManualCompanyProvider, ManualReportProvider


class DiscoveryRegistry:
    def __init__(self) -> None:
        self._search: list[CompanySearchProvider] = []
        self._discovery: list[AnnualReportDiscoveryProvider] = []

    def register_search(self, provider: CompanySearchProvider) -> None:
        self._search.append(provider)

    def register_discovery(self, provider: AnnualReportDiscoveryProvider) -> None:
        self._discovery.append(provider)

    def search_companies(self, query: str) -> list[CompanyMatch]:
        out: list[CompanyMatch] = []
        for p in self._search:
            try:
                out.extend(p.search(query))
            except Exception:
                continue
        return out

    def discover_reports(self, company: CompanyMatch, start_fy: str, end_fy: str) -> list[ReportListing]:
        out: list[ReportListing] = []
        for p in self._discovery:
            try:
                out.extend(p.discover(company, start_fy, end_fy))
            except Exception:
                continue
        return out


def default_registry() -> DiscoveryRegistry:
    reg = DiscoveryRegistry()
    reg.register_search(ManualCompanyProvider())
    reg.register_discovery(ManualReportProvider())
    return reg
