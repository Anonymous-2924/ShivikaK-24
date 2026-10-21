"""Gold-table loader: data/gold/<basename>.{parquet,schema.json,sha256}

Verifies the sha256 on every ingest. A mismatch is a HARD error — the
whole gold load fails loudly. Verified gold tables are copied into
``data/processed/numeric/`` with ``extraction_method="manual"`` and
``confidence=1.0``. Phase 4's graph build trusts these outright.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq


class GoldChecksumMismatch(RuntimeError):
    pass


@dataclass(frozen=True)
class GoldTable:
    basename: str
    parquet_src: Path
    schema: dict
    rows: int


def scan(gold_dir: Path) -> list[GoldTable]:
    """Enumerate verified gold tables. Raises on checksum mismatch."""
    out: list[GoldTable] = []
    if not gold_dir.exists():
        return out
    for parquet in sorted(gold_dir.glob("*.parquet")):
        base = parquet.stem
        schema_path = gold_dir / f"{base}.schema.json"
        sha_path = gold_dir / f"{base}.sha256"
        if not schema_path.exists() or not sha_path.exists():
            # Partially-staged gold entries are a user error — flag loudly
            # rather than silently skip.
            raise FileNotFoundError(
                f"gold table '{base}' is missing a sidecar file "
                f"(need both {schema_path.name} and {sha_path.name})"
            )
        actual = _sha256(parquet)
        expected = _parse_sha(sha_path)
        if actual != expected:
            raise GoldChecksumMismatch(
                f"gold table {base}: sha256 mismatch "
                f"(expected {expected}, got {actual})"
            )
        schema = json.loads(schema_path.read_text())
        table = pq.read_table(parquet)
        out.append(GoldTable(basename=base, parquet_src=parquet,
                              schema=schema, rows=table.num_rows))
    return out


def install(table: GoldTable, dest_dir: Path) -> Path:
    """Copy the parquet into the processed/numeric tree. Returns dest path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / table.parquet_src.name
    shutil.copy2(table.parquet_src, dest)
    return dest


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 64), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_sha(sha_path: Path) -> str:
    # Format: "<64-hex>  <filename>" (plain `shasum` output)
    first = sha_path.read_text().strip().splitlines()[0].strip()
    return first.split()[0].lower()
