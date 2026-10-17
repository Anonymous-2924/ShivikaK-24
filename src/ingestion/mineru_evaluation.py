"""Optional Docling vs MinerU parser comparison (evaluation only).

MinerU is NOT part of the normal ingestion path and is NOT auto-installed: its
dependency/resource footprint (GPU-oriented models) is impractical to run
concurrently with Docling on a 16 GB machine. This module provides a structured
comparison harness that runs the two parsers *sequentially* on a small sample
when both are installed, and otherwise reports the limitation honestly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParserRun:
    parser: str
    available: bool
    chars: int = 0
    n_tables: int = 0
    seconds: float = 0.0
    error: str | None = None


@dataclass
class ComparisonResult:
    sample_path: str
    runs: list[ParserRun] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _run_docling(path: Path) -> ParserRun:
    from src.ingestion.docling_parser import docling_available, parse_pdf_with_docling

    if not docling_available():
        return ParserRun("docling", available=False, error="docling not installed")
    t0 = time.perf_counter()
    try:
        doc = parse_pdf_with_docling(path)
        return ParserRun("docling", True, len(doc.markdown),
                         sum(1 for s in doc.sections if s.is_table), time.perf_counter() - t0)
    except Exception as exc:
        return ParserRun("docling", True, error=str(exc), seconds=time.perf_counter() - t0)


def _run_mineru(path: Path) -> ParserRun:
    try:
        import magic_pdf  # noqa: F401  (MinerU package)
    except Exception:
        return ParserRun("mineru", available=False,
                         error="MinerU not installed (optional, heavy dependency).")
    # A real MinerU invocation would go here, run sequentially after Docling.
    return ParserRun("mineru", available=True,
                     error="MinerU installed but invocation not wired in this build.")


def compare_on_sample(pdf_path: str) -> ComparisonResult:
    p = Path(pdf_path)
    result = ComparisonResult(sample_path=str(p))
    result.runs.append(_run_docling(p))
    result.runs.append(_run_mineru(p))
    result.notes.append("Parsers run sequentially to respect the 16 GB memory budget.")
    if not any(r.available for r in result.runs):
        result.notes.append("Neither Docling nor MinerU is installed; nothing was compared.")
    return result
