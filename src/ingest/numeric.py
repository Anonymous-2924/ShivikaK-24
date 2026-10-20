"""Numeric-track parsers: Excel, CSV/TSV. ERP JSON/XML live in ``structured.py``.

Everything here produces Parquet (via pyarrow directly — not pandas) plus
a short Markdown data card. The data card is what gets embedded in Qdrant;
the Parquet file is what Phase 5 agents run SQL against.
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


@dataclass
class NumericTable:
    """One table ready for the numeric track."""
    sheet_or_name: str
    columns: list[str]
    rows: list[list[Any]]        # python-native values; pyarrow infers types
    confidence: float
    extractor: str
    note: str | None = None
    inferred_dtypes: list[str] = field(default_factory=list)  # filled by write()

    def write_parquet(self, dest: Path) -> int:
        """Write to parquet; return row count."""
        if not self.rows:
            # Still write an empty table so Phase 4 can see the schema.
            table = pa.table({c: pa.array([], type=pa.string())
                              for c in self.columns})
        else:
            # Build column-wise, infer type per column with pyarrow.
            cols: dict[str, pa.Array] = {}
            for i, name in enumerate(self.columns):
                vals = [r[i] if i < len(r) else None for r in self.rows]
                cols[name] = _best_pa_array(vals)
            table = pa.table(cols)
        self.inferred_dtypes = [str(f.type) for f in table.schema]
        dest.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, dest)
        return table.num_rows


def parse_excel(path: Path) -> list[NumericTable]:
    """Each sheet becomes one NumericTable. Merged header cells are
    de-merged (value broadcasts to the merge range) and the first non-
    empty row becomes the column header.

    Formula cells are read as their *stored* text (``=SUM(...)``). Phase
    4 can decide whether to resolve them; the data card flags their
    presence so semantic search can find spreadsheets that compute.
    """
    from openpyxl import load_workbook
    wb = load_workbook(filename=str(path), data_only=False, read_only=True)
    tables: list[NumericTable] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows_raw: list[list[Any]] = []
        for row in ws.iter_rows(values_only=True):
            rows_raw.append(list(row))
        if not rows_raw:
            tables.append(NumericTable(
                sheet_or_name=sheet_name, columns=[], rows=[],
                confidence=0.0, extractor="openpyxl",
                note="empty sheet",
            ))
            continue
        # Find the first row that has at least two non-None cells — that's
        # the header. Everything before it is title/subtitle noise.
        header_row_idx = 0
        for i, r in enumerate(rows_raw):
            nonempty = sum(1 for c in r if c not in (None, ""))
            if nonempty >= 2:
                header_row_idx = i
                break
        header = [str(c).strip() if c is not None else f"col_{i}"
                  for i, c in enumerate(rows_raw[header_row_idx])]
        # Drop trailing empty columns in the header to keep schema sane.
        while header and (header[-1].startswith("col_") or header[-1] == ""):
            header.pop()
        body = rows_raw[header_row_idx + 1:]
        # Trim rows to header width and skip entirely-empty rows.
        clean_body: list[list[Any]] = []
        for r in body:
            trimmed = list(r)[: len(header)]
            if any(c not in (None, "") for c in trimmed):
                clean_body.append(trimmed)
        tables.append(NumericTable(
            sheet_or_name=sheet_name, columns=header, rows=clean_body,
            confidence=_excel_sheet_confidence(header, clean_body),
            extractor="openpyxl",
        ))
    wb.close()
    return tables


def parse_csv(path: Path) -> list[NumericTable]:
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=delim)
        rows_raw = list(reader)
    if not rows_raw:
        return [NumericTable(sheet_or_name=path.stem, columns=[], rows=[],
                             confidence=0.0, extractor="csv",
                             note="empty file")]
    header, body = rows_raw[0], rows_raw[1:]
    header = [h.strip() if h else f"col_{i}" for i, h in enumerate(header)]
    conf = _csv_confidence(header, body)
    return [NumericTable(sheet_or_name=path.stem, columns=header,
                          rows=body, confidence=conf, extractor="csv")]


def _excel_sheet_confidence(header: list[str], body: list[list[Any]]) -> float:
    if not header:
        return 0.1
    if not body:
        return 0.5
    uniq = len(set(h.lower() for h in header)) / max(1, len(header))
    # Fraction of rows whose length matches the header.
    width_consistent = sum(1 for r in body if len(r) == len(header)) / len(body)
    return round(0.55 + 0.25 * uniq + 0.20 * width_consistent, 3)


def _csv_confidence(header: list[str], body: list[list[str]]) -> float:
    if not header or not body:
        return 0.3
    uniq = len(set(h.lower() for h in header)) / max(1, len(header))
    width_consistent = sum(1 for r in body if len(r) == len(header)) / len(body)
    return round(0.60 + 0.25 * uniq + 0.15 * width_consistent, 3)


# ---------- Type inference ----------
def _best_pa_array(values: list[Any]) -> pa.Array:
    """Pick the strictest pyarrow type that holds every non-None value.

    Order of attempt: int64 → float64 → date32 → timestamp[s] → string.
    Blank strings count as nulls.
    """
    cleaned: list[Any] = [None if (v is None or (isinstance(v, str) and not v.strip()))
                           else v for v in values]
    # Already-typed values short-circuit.
    if any(isinstance(v, (dt.datetime,)) for v in cleaned if v is not None):
        return pa.array(cleaned, type=pa.timestamp("s"))
    if any(isinstance(v, dt.date) for v in cleaned if v is not None):
        return pa.array(cleaned, type=pa.date32())
    if all(isinstance(v, int) or v is None for v in cleaned):
        try:
            return pa.array(cleaned, type=pa.int64())
        except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError):
            pass
    if all(isinstance(v, (int, float)) or v is None for v in cleaned):
        try:
            return pa.array([float(v) if v is not None else None for v in cleaned],
                            type=pa.float64())
        except (pa.ArrowInvalid, pa.ArrowTypeError):
            pass
    # String-typed path: try numeric parsing on string values.
    str_vals = [None if v is None else str(v) for v in cleaned]
    as_int = _try_parse_all(str_vals, int)
    if as_int is not None:
        return pa.array(as_int, type=pa.int64())
    as_float = _try_parse_all(str_vals, float)
    if as_float is not None:
        return pa.array(as_float, type=pa.float64())
    as_date = _try_parse_all(str_vals, _parse_date)
    if as_date is not None:
        return pa.array(as_date, type=pa.date32())
    return pa.array(str_vals, type=pa.string())


def _try_parse_all(values: list[str | None], fn):
    out: list[Any] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        try:
            out.append(fn(v))
        except (ValueError, TypeError):
            return None
    # Must have at least one parsed value for the attempt to count.
    if all(v is None for v in out):
        return None
    return out


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)
