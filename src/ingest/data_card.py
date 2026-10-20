"""Markdown data card for every numeric asset.

The card is the semantic-search entry-point to a table. Phase 5 agents
search Qdrant and get back the card; the card points at the Parquet path
they then query via DuckDB. The card itself holds no numbers — just
schema, units, provenance, caveats, and a tiny sample.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.ingest.numeric import NumericTable


def write_data_card(
    *, out_path: Path, parquet_path: Path, source_file: Path,
    table: NumericTable, row_count: int, extraction_method: str,
    confidence: float, period: str | None = None,
    linked_entities: list[str] | None = None,
) -> str:
    """Write the data card next to the parquet and return its text."""
    md = _render(
        parquet_path=parquet_path, source_file=source_file,
        table=table, row_count=row_count,
        extraction_method=extraction_method, confidence=confidence,
        period=period, linked_entities=linked_entities,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    return md


def _render(*, parquet_path: Path, source_file: Path, table: NumericTable,
            row_count: int, extraction_method: str, confidence: float,
            period: str | None, linked_entities: list[str] | None) -> str:
    lines: list[str] = []
    lines.append(f"# DataTable: {parquet_path.stem}")
    lines.append("")
    lines.append(f"- **Source file:** `{source_file.name}`")
    lines.append(f"- **Sheet / record set:** `{table.sheet_or_name}`")
    lines.append(f"- **Parquet:** `{parquet_path.name}`")
    lines.append(f"- **Rows:** {row_count}")
    lines.append(f"- **Columns:** {len(table.columns)}")
    lines.append(f"- **Extraction method:** {extraction_method}")
    lines.append(f"- **Extractor:** {table.extractor}")
    lines.append(f"- **Confidence:** {confidence:.2f}")
    if period:
        lines.append(f"- **Period:** {period}")
    if linked_entities:
        lines.append(f"- **Linked entities:** {', '.join(linked_entities)}")
    if table.note:
        lines.append(f"- **Caveat:** {table.note}")
    lines.append("")
    lines.append("## Schema")
    lines.append("")
    lines.append("| Column | Dtype |")
    lines.append("|---|---|")
    for name, dtype in zip(table.columns,
                           table.inferred_dtypes or ["?"] * len(table.columns),
                           strict=False):
        lines.append(f"| {name} | {dtype} |")
    lines.append("")
    lines.append("## Sample rows (first 5)")
    lines.append("")
    if not table.rows:
        lines.append("_(no rows)_")
    else:
        lines.append("| " + " | ".join(table.columns) + " |")
        lines.append("|" + "|".join([" --- "] * len(table.columns)) + "|")
        for r in table.rows[:5]:
            cells = [_fmt_cell(c) for c in r][: len(table.columns)]
            # pad to column count
            cells += [""] * (len(table.columns) - len(cells))
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def _fmt_cell(v: Any) -> str:
    if v is None:
        return ""
    s = str(v)
    # Keep pipe-tables well-formed and prevent runaway wide cells.
    s = s.replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= 80 else s[:77] + "..."
