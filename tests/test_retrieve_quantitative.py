"""Quantitative dispatcher: real DuckDB against a real temp Parquet file
(fast, local, no server needed) + a fake Neo4j driver for the lookup."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.retrieve.quantitative import find_datatable_for_entity, run_metric


@pytest.fixture
def revenue_parquet(tmp_path: Path) -> Path:
    path = tmp_path / "financials.parquet"
    table = pa.table({
        "period": ["2026-01", "2026-02", "2026-03"],
        "revenue_usd": [100.0, 150.0, 200.0],
        "buffer_days": [12, 9, 15],
    })
    pq.write_table(table, path)
    return path


def test_run_metric_discovers_matching_column(revenue_parquet: Path):
    conn = duckdb.connect()
    result = run_metric(conn, str(revenue_parquet), "revenue")
    assert result.column_used == "revenue_usd"
    assert result.result["total"] == pytest.approx(450.0)
    assert result.result["n_rows"] == 3


def test_run_metric_buffer_days(revenue_parquet: Path):
    conn = duckdb.connect()
    result = run_metric(conn, str(revenue_parquet), "buffer_days")
    assert result.column_used == "buffer_days"
    assert result.result["average"] == pytest.approx(12.0)
    assert result.result["min"] == 9
    assert result.result["max"] == 15


def test_run_metric_no_matching_column_returns_none_result(tmp_path: Path):
    path = tmp_path / "no_financials.parquet"
    pq.write_table(pa.table({"garment_type": ["jacket", "tee"]}), path)
    conn = duckdb.connect()
    result = run_metric(conn, str(path), "revenue")
    assert result.result is None
    assert result.column_used is None
    assert "no column matching" in result.note


def test_run_metric_rejects_unknown_metric_name(revenue_parquet: Path):
    conn = duckdb.connect()
    with pytest.raises(ValueError):
        run_metric(conn, str(revenue_parquet), "not_a_real_metric")


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def run(self, cypher, **params):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeDriver:
    def __init__(self, rows):
        self.rows = rows

    def session(self, database):
        return _FakeSession(self.rows)


def test_find_datatable_for_entity_returns_parquet_paths():
    driver = _FakeDriver([
        {"table_id": "TBL-1", "parquet_path": "/data/x.parquet"},
    ])
    tables = find_datatable_for_entity(driver, "SUP-0001")
    assert tables == [{"table_id": "TBL-1", "parquet_path": "/data/x.parquet"}]
