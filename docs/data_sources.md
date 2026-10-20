# Data Sources & Discovery Policy

## Why automated scraping is not shipped
The master requirements point to NSE (nseindia.com), BSE (bseindia.com) and
Screener (screener.in). These sites use access controls, bot protections and
terms of use that **prohibit automated bypass**. Shipping a scraper that
defeats those controls would be wrong, and fabricating listings would violate
the project's core anti-hallucination rule. So this build does **not** scrape
them.

What it ships instead:
- **Provider interfaces** (`src/ingestion/source_adapters/base.py`):
  `CompanySearchProvider`, `AnnualReportDiscoveryProvider`,
  `AnnualReportDownloadProvider`. A compliant official-source adapter can be
  added here later against a documented, permitted mechanism (e.g. an official
  API or an investor-relations page that permits automated access), respecting
  robots.txt, rate limits and terms.
- **A manual adapter** (`manual.py`) — the fully supported path:
  - upload a PDF/DOCX/XLSX/CSV (Document Management), or
  - paste a direct official report URL (Report Discovery).
- **SSRF-guarded downloads** (`downloader.py`): http/https only, private/
  loopback/link-local hosts blocked, size + timeout limits.

## Provenance stored per report
company, company id, ticker, exchange, financial year, period start/end,
publication date, official source URL, original filename, local path,
SHA-256 checksum, file size, download timestamp, document/parse/index status,
standalone-vs-consolidated (when known), verification status + warnings.

## Honesty rules
- A report is **not** marked `verified_official` until a human confirms the
  source. Manual entries stay unverified by default.
- A filename containing a year does **not** imply a complete 12-month period;
  transition/restated/amended/ambiguous periods must be flagged.
- Screener (where used in future) is for discovery and cross-checking only —
  never a substitute for the official annual report.
