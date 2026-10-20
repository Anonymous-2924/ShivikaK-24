"""Gold-table loader: schema sidecar + checksum verification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.ingest import gold


def _write_gold_triple(dir_: Path, basename: str,
                       table: pa.Table, schema: dict,
                       *, correct_sha: bool = True) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    parquet = dir_ / f"{basename}.parquet"
    pq.write_table(table, parquet)
    actual = hashlib.sha256(parquet.read_bytes()).hexdigest()
    sha_val = actual if correct_sha else "0" * 64
    (dir_ / f"{basename}.sha256").write_text(f"{sha_val}  {basename}.parquet\n")
    (dir_ / f"{basename}.schema.json").write_text(json.dumps(schema))


def test_gold_scan_loads_valid_tables(tmp_path: Path) -> None:
    tbl = pa.table({"part": pa.array(["P1", "P2"]),
                    "qty": pa.array([1, 2])})
    schema = {"basename": "acme_bom",
              "entity_type": "DataTable",
              "linked_entity": "Supplier:ACME",
              "columns": [{"name": "part", "dtype": "string"},
                          {"name": "qty",  "dtype": "int64"}]}
    _write_gold_triple(tmp_path, "acme_bom", tbl, schema)
    tables = gold.scan(tmp_path)
    assert len(tables) == 1
    assert tables[0].basename == "acme_bom"
    assert tables[0].rows == 2


def test_gold_scan_rejects_checksum_mismatch(tmp_path: Path) -> None:
    tbl = pa.table({"a": pa.array([1, 2, 3])})
    _write_gold_triple(tmp_path, "bad", tbl, {}, correct_sha=False)
    with pytest.raises(gold.GoldChecksumMismatch):
        gold.scan(tmp_path)


def test_gold_scan_rejects_missing_sidecar(tmp_path: Path) -> None:
    tbl = pa.table({"a": pa.array([1])})
    pq.write_table(tbl, tmp_path / "lonely.parquet")
    with pytest.raises(FileNotFoundError):
        gold.scan(tmp_path)


def test_gold_install_copies_parquet(tmp_path: Path) -> None:
    tbl = pa.table({"a": pa.array([1, 2])})
    schema = {"columns": []}
    _write_gold_triple(tmp_path, "demo", tbl, schema)
    tables = gold.scan(tmp_path)
    dest_dir = tmp_path / "processed"
    dest = gold.install(tables[0], dest_dir)
    assert dest.exists()
    assert pq.read_table(dest).num_rows == 2
