"""Batch-ingest local report files into the index.

Run:  python scripts/ingest_reports.py --company "Example Ltd" --fy FY2023-24 path/to/report.pdf
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.context import build_context
from src.services.document_service import DocumentService


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--company", required=True)
    ap.add_argument("--fy", default=None)
    ap.add_argument("--basis", default="unknown", choices=["unknown", "consolidated", "standalone"])
    ap.add_argument("--report-type", default="Annual Report")
    args = ap.parse_args()

    ctx = build_context()
    svc = DocumentService(ctx)
    rc = 0
    for f in args.files:
        try:
            out = svc.add_file(f, company_name=args.company, financial_year=args.fy,
                               basis=args.basis, report_type=args.report_type)
            if out.duplicate:
                print(f"[dup] {f}: {out.message}")
            else:
                n = out.result.chunks_indexed if out.result else 0
                print(f"[ok]  {f}: {out.message} ({n} chunks)")
                if out.result and out.result.parse_warnings:
                    print("      warnings:", "; ".join(out.result.parse_warnings))
        except Exception as exc:
            print(f"[err] {f}: {exc}"); rc = 1
    print("Stats:", ctx.metadata_store.stats())
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
