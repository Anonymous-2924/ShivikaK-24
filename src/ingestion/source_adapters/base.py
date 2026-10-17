"""Provider interfaces for company discovery and annual-report ingestion.

These abstract base classes define the contract every source adapter must
implement. Concrete official-source adapters (NSE/BSE/investor-relations) are
intentionally NOT shipped with fabricated endpoints — see
``docs/data_sources.md`` for why, and the manual adapter for the supported
path. Implement real adapters here only against documented, permitted access
mechanisms that respect robots.txt, terms and rate limits.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompanyMatch:
    name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    company_id: Optional[str] = None
    source: str = "unknown"
    confidence: float = 0.0


@dataclass
class ReportListing:
    company_name: str
    financial_year: str
    title: str
    source_url: Optional[str] = None
    exchange: Optional[str] = None
    publication_date: Optional[str] = None
    source: str = "unknown"
    verified_official: bool = False  # True only when provenance is confirmed
    notes: list[str] = field(default_factory=list)


class CompanySearchProvider(ABC):
    name: str = "base"

    @abstractmethod
    def search(self, query: str) -> list[CompanyMatch]:
        ...


class AnnualReportDiscoveryProvider(ABC):
    name: str = "base"

    @abstractmethod
    def discover(self, company: CompanyMatch, start_fy: str, end_fy: str) -> list[ReportListing]:
        ...


class AnnualReportDownloadProvider(ABC):
    name: str = "base"

    @abstractmethod
    def download(self, listing: ReportListing, dest_dir: str):
        ...
