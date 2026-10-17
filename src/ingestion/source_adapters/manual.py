"""Manual provider: the fully-supported ingestion path.

The user supplies company details and either uploads a PDF or provides a direct
report URL. No scraping, no fabricated listings — provenance is exactly what
the user provides, and remains ``verified_official=False`` until a human
confirms the source is official.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.ingestion.downloader import download as http_download
from src.ingestion.source_adapters.base import (
    AnnualReportDiscoveryProvider,
    AnnualReportDownloadProvider,
    CompanyMatch,
    CompanySearchProvider,
    ReportListing,
)


class ManualCompanyProvider(CompanySearchProvider):
    name = "manual"

    def search(self, query: str) -> list[CompanyMatch]:
        # Manual mode echoes the user's own entry as a candidate; it does not
        # invent matches or claim an exchange it cannot verify.
        q = query.strip()
        if not q:
            return []
        return [CompanyMatch(name=q, source="manual", confidence=1.0)]


class ManualReportProvider(AnnualReportDiscoveryProvider, AnnualReportDownloadProvider):
    name = "manual"

    def discover(self, company: CompanyMatch, start_fy: str, end_fy: str) -> list[ReportListing]:
        # Manual discovery returns nothing to fetch automatically; the user
        # adds reports via upload or an explicit URL.
        return []

    def make_listing(
        self, company_name: str, financial_year: str, source_url: Optional[str] = None,
        title: Optional[str] = None, exchange: Optional[str] = None,
    ) -> ReportListing:
        return ReportListing(
            company_name=company_name,
            financial_year=financial_year,
            title=title or f"{company_name} {financial_year} (manual)",
            source_url=source_url,
            exchange=exchange,
            source="manual",
            verified_official=False,
            notes=["Source provided manually; mark as official only after human verification."],
        )

    def download(self, listing: ReportListing, dest_dir: str):
        if not listing.source_url:
            raise ValueError("Manual download requires a source_url on the listing.")
        return http_download(listing.source_url, dest_dir)
