"""CSV, Excel, and ERP-style JSON/XML parsing with dtype inference."""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

import pyarrow.parquet as pq
import pytest

from src.ingest import numeric, structured


def test_csv_parses_and_infers_types(tmp_path: Path) -> None:
    p = tmp_path / "lead.csv"
    p.write_text(
        "supplier_id,month,avg_lead_days,otd_pct\n"
        "SUP-T1-0001,2026-04-01,42,0.91\n"
        "SUP-T1-0002,2026-04-01,37,0.95\n"
        "SUP-T1-0003,2026-04-01,55,0.80\n",
        encoding="utf-8",
    )
    tables = numeric.parse_csv(p)
    assert len(tables) == 1
    t = tables[0]
    assert t.columns == ["supplier_id", "month", "avg_lead_days", "otd_pct"]
    assert t.confidence > 0.75
    out = tmp_path / "out.parquet"
    rows = t.write_parquet(out)
    assert rows == 3
    tbl = pq.read_table(out)
    # supplier_id stays string, month → date32, lead → int64, otd → float64.
    dtypes = {name: str(tbl.schema.field(name).type) for name in tbl.column_names}
    assert dtypes["supplier_id"] == "string"
    assert dtypes["month"] == "date32[day]"
    assert dtypes["avg_lead_days"] == "int64"
    assert dtypes["otd_pct"] == "double"


def test_excel_parses_each_sheet(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook
    wb = Workbook()
    ws1 = wb.active
    assert ws1 is not None
    ws1.title = "Sheet A"
    ws1.append(["id", "qty"])
    ws1.append(["A1", 5])
    ws1.append(["A2", 7])
    ws2 = wb.create_sheet("Sheet B")
    ws2.append(["x", "y", "z"])
    ws2.append([1, 2.5, "note"])
    xlsx = tmp_path / "two.xlsx"
    wb.save(xlsx)
    tables = numeric.parse_excel(xlsx)
    assert len(tables) == 2
    names = sorted(t.sheet_or_name for t in tables)
    assert names == ["Sheet A", "Sheet B"]
    a = next(t for t in tables if t.sheet_or_name == "Sheet A")
    assert a.columns == ["id", "qty"]
    assert len(a.rows) == 2
    assert a.confidence > 0.7


def test_json_finds_record_list_and_flattens(tmp_path: Path) -> None:
    data = {
        "export_from": "ERP",
        "exported_at": "2026-09-30T23:59Z",
        "suppliers": [
            {"id": "S1", "tier": 1, "country": "BD", "capacity": 1_000_000},
            {"id": "S2", "tier": 1, "country": "VN", "capacity": 500_000},
            {"id": "S3", "tier": 2, "country": "IN", "capacity": 10_000_000},
        ],
    }
    p = tmp_path / "export.json"
    p.write_text(json.dumps(data))
    tables = structured.parse_json(p)
    assert len(tables) == 1
    t = tables[0]
    assert t.sheet_or_name == "suppliers"
    assert set(t.columns) == {"id", "tier", "country", "capacity"}
    assert len(t.rows) == 3
    out = tmp_path / "out.parquet"
    rows = t.write_parquet(out)
    assert rows == 3


def test_xml_finds_record_tag(tmp_path: Path) -> None:
    root = Element("Export")
    for i, cc in enumerate(["BD", "VN", "IN"], start=1):
        node = SubElement(root, "Plant", attrib={"id": f"PLT-{i}"})
        SubElement(node, "CountryCode").text = cc
        SubElement(node, "Lines").text = str(i * 3)
    p = tmp_path / "plants.xml"
    ElementTree(root).write(p, encoding="utf-8", xml_declaration=True)
    tables = structured.parse_xml(p)
    assert len(tables) == 1
    t = tables[0]
    assert t.sheet_or_name == "Plant"
    assert "id" in t.columns and "CountryCode" in t.columns
    assert len(t.rows) == 3
