"""Structured-track parsers: JSON and XML ERP-style exports.

These are shaped like numeric data but arrive as nested objects. We flatten
the dominant list of records to a NumericTable so the rest of the pipeline
treats them uniformly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import parse as xml_parse

from src.ingest.numeric import NumericTable


def parse_json(path: Path) -> list[NumericTable]:
    """Find the first list-of-dicts in the file and flatten it."""
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    records, picked_key = _find_record_list(data)
    if not records:
        return [NumericTable(sheet_or_name=path.stem, columns=[], rows=[],
                              confidence=0.3, extractor="json",
                              note="no record list found")]
    header, rows = _records_to_rows(records)
    name = picked_key or path.stem
    conf = round(0.75 + 0.20 * (len({tuple(sorted(r.keys())) for r in records}) == 1),
                 3)
    return [NumericTable(sheet_or_name=name, columns=header, rows=rows,
                          confidence=conf, extractor="json")]


def parse_xml(path: Path) -> list[NumericTable]:
    tree = xml_parse(path)
    root = tree.getroot()
    # Group children by tag; the largest group is the record set.
    by_tag: dict[str, list] = {}
    for child in root:
        by_tag.setdefault(child.tag, []).append(child)
    if not by_tag:
        return [NumericTable(sheet_or_name=path.stem, columns=[], rows=[],
                              confidence=0.3, extractor="xml",
                              note="no child records")]
    records_tag, records = max(by_tag.items(), key=lambda kv: len(kv[1]))
    dict_records: list[dict[str, Any]] = []
    for r in records:
        flat: dict[str, Any] = dict(r.attrib)
        for leaf in r:
            if list(leaf):
                # Child-of-child: concatenate inner text values.
                flat[leaf.tag] = "; ".join(
                    (sub.text or "").strip() for sub in leaf
                )
            else:
                flat[leaf.tag] = (leaf.text or "").strip()
        dict_records.append(flat)
    header, rows = _records_to_rows(dict_records)
    conf = 0.80 if len({tuple(sorted(d.keys())) for d in dict_records}) == 1 else 0.65
    return [NumericTable(sheet_or_name=records_tag or path.stem,
                          columns=header, rows=rows,
                          confidence=conf, extractor="xml")]


# ---------- helpers ----------
def _find_record_list(obj: Any) -> tuple[list[dict] | None, str | None]:
    if isinstance(obj, list) and obj and all(isinstance(r, dict) for r in obj):
        return obj, None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and v and all(isinstance(r, dict) for r in v):
                return v, k
            found, name = _find_record_list(v)
            if found:
                return found, name or k
    return None, None


def _records_to_rows(records: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    header: list[str] = []
    seen: set[str] = set()
    for r in records:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                header.append(k)
    rows: list[list[Any]] = []
    for r in records:
        rows.append([_scalarise(r.get(k)) for k in header])
    return header, rows


def _scalarise(v: Any) -> Any:
    """Keep primitives; stringify nested structures so the row is flat."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    try:
        return json.dumps(v, sort_keys=True)
    except TypeError:
        return str(v)
