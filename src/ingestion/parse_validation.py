"""Post-parse quality checks that surface (never hide) extraction problems."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.ingestion.parser import ParsedDocument


@dataclass
class ParseQuality:
    ok: bool
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def validate_parse(doc: ParsedDocument, *, source_size_bytes: int | None = None) -> ParseQuality:
    warnings = list(doc.warnings)
    stats = {
        "chars": doc.total_chars,
        "pages": len(doc.pages),
        "sections": len(doc.sections),
        "tables": sum(1 for s in doc.sections if s.is_table),
    }

    if doc.total_chars == 0:
        warnings.append("Empty extraction — no text was produced.")

    # Implausibly small output vs source size (heuristic).
    if source_size_bytes and source_size_bytes > 200_000 and doc.total_chars < 500:
        warnings.append(
            f"Output suspiciously small ({doc.total_chars} chars) for a "
            f"{source_size_bytes/1e6:.1f} MB source — possible scanned/image PDF."
        )

    # Missing page mapping for a multi-page PDF.
    if doc.parser_name == "pdfplumber" and doc.pages and all(not p.text.strip() for p in doc.pages):
        warnings.append("All pages empty — document likely needs OCR.")

    # Repeated header/footer detection (same short line on many pages).
    if len(doc.pages) >= 3:
        first_lines = [p.text.strip().split("\n", 1)[0] for p in doc.pages if p.text.strip()]
        if first_lines:
            from collections import Counter

            common, count = Counter(first_lines).most_common(1)[0]
            if count >= max(3, len(first_lines) // 2) and len(common) < 80:
                warnings.append(f"Repeated header/footer detected: '{common[:60]}'.")

    # Malformed tables (rows with wildly varying column counts).
    for s in doc.sections:
        if s.is_table and s.text.count("\n") >= 2:
            rows = [r for r in s.text.splitlines() if r.strip().startswith("|")]
            if rows:
                widths = {r.count("|") for r in rows}
                if len(widths) > 2:  # header + sep + body allow 1-2 patterns
                    warnings.append(f"Possibly malformed table on page {s.page_number}.")
                    break

    ok = doc.total_chars > 0
    return ParseQuality(ok=ok, warnings=warnings, stats=stats)
