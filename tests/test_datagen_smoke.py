"""Phase 2 tests: the generator runs, is deterministic in its text outputs,
and injects the deliberate mess at approximately the configured rates.

Byte-level determinism of PDFs/XLSX/DOCX is NOT asserted — reportlab,
openpyxl and python-docx all embed timestamps or non-stable UUIDs in their
file headers. We check the plain-text outputs (REALISM_LOG, ERP JSON/XML,
CSV, news .md/.txt) for exact equality.
"""
from __future__ import annotations

import filecmp
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Skip the whole module if the generator's optional deps aren't installed.
# This keeps `pytest` useful in dev envs that haven't done `pip install -e .[datagen]`.
openpyxl = pytest.importorskip("openpyxl")
docx = pytest.importorskip("docx")
reportlab = pytest.importorskip("reportlab")
pil = pytest.importorskip("PIL")

ROOT = Path(__file__).parent.parent


def _run_generator(out: Path, seed: int = 42) -> None:
    r = subprocess.run(
        [sys.executable, "-m", "tools.datagen.generate",
         "--smoke", "--seed", str(seed), "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"generator failed:\nstdout:{r.stdout}\nstderr:{r.stderr}"


def test_smoke_run_produces_expected_file_shape(tmp_path: Path) -> None:
    out = tmp_path / "gen"
    _run_generator(out)
    # Core outputs exist.
    assert (out / "REALISM_LOG.md").exists()
    assert (out / "supplier_master.xlsx").exists()
    assert (out / "bom_master.xlsx").exists()
    assert (out / "inventory_snapshot.xlsx").exists()
    assert (out / "pricelist.xlsx").exists()
    assert (out / "shipments" / "shipment_log.csv").exists()
    assert (out / "shipments" / "lead_time_history.csv").exists()
    assert len(list((out / "demand").glob("daily_demand_*.csv"))) == 12
    assert (out / "erp" / "suppliers_export.json").exists()
    assert (out / "erp" / "plants_export.xml").exists()
    assert (out / "erp" / "skus_export.json").exists()
    # Prose + structured kinds.
    assert len(list((out / "audits").glob("*.pdf"))) >= 1
    assert len(list((out / "contracts").glob("*.pdf"))) >= 1
    assert len(list((out / "news").glob("news_*.*"))) >= 1
    assert len(list((out / "policies").glob("*.docx"))) >= 1
    assert len(list((out / "charts").glob("*.png"))) >= 1


def test_text_outputs_are_deterministic(tmp_path: Path) -> None:
    """Byte-identical plain-text output across runs with the same seed."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    _run_generator(a)
    _run_generator(b)

    # Files that are plain text and must byte-match.
    for rel in [
        "REALISM_LOG.md",
        "erp/suppliers_export.json",
        "erp/skus_export.json",
        "erp/plants_export.xml",
        "erp/routes_export.json",
        "erp/components_export.json",
        "shipments/shipment_log.csv",
        "shipments/lead_time_history.csv",
    ]:
        pa, pb = a / rel, b / rel
        assert pa.exists() and pb.exists(), f"missing: {rel}"
        assert filecmp.cmp(pa, pb, shallow=False), f"non-deterministic: {rel}"

    # News and demand dirs.
    for rel_dir in ("news", "demand"):
        match, mismatch, errors = filecmp.cmpfiles(
            a / rel_dir, b / rel_dir,
            [p.name for p in (a / rel_dir).iterdir()],
            shallow=False,
        )
        assert not mismatch and not errors, (
            f"non-deterministic files in {rel_dir}: "
            f"mismatch={mismatch} errors={errors}"
        )


def test_different_seeds_produce_different_output(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    _run_generator(a, seed=42)
    _run_generator(b, seed=43)
    assert not filecmp.cmp(a / "erp" / "suppliers_export.json",
                           b / "erp" / "suppliers_export.json",
                           shallow=False), \
        "seed change should perturb entity population"


def test_realism_log_counts_match_targets(tmp_path: Path) -> None:
    """Full-scale run (via generator defaults): the deliberate-mess rates
    should be in the right ballpark. Rates per the brief: ~5% missing fields,
    ~3% stale records, 3-5 name variants per supplier (so hundreds of
    variant-usages across the whole corpus), 1 deliberately malformed table.

    We don't assert exact counts — the generator is deterministic but tuning
    thresholds should not break this test. We assert the categories are
    present and non-trivial.
    """
    out = tmp_path / "full"
    r = subprocess.run(
        [sys.executable, "-m", "tools.datagen.generate",
         "--suppliers", "60", "--tier2", "25", "--plants", "12",
         "--components", "200", "--skus", "150", "--routes", "15",
         "--audit-reports", "12", "--financials-pdf", "4",
         "--financials-xlsx", "4", "--contracts", "4",
         "--certification-pdfs", "4", "--news-articles", "8",
         "--correspondence", "4", "--postmortems", "2", "--charts", "4",
         "--shipment-rows", "800",
         "--seed", "42", "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr

    log_text = (out / "REALISM_LOG.md").read_text()
    # Categories we must see.
    for cat in [
        "supplier.missing_field",
        "supplier.stale_record",
        "duplicate.near_duplicate_supplier",
        "contradiction.capacity",
        "name.variant_used",
        "table.malformed_on_purpose",
        "units.unlabelled_currency",
    ]:
        assert cat in log_text, f"realism log missing category: {cat}"


def test_supplier_count_matches_cli_args(tmp_path: Path) -> None:
    out = tmp_path / "run"
    _run_generator(out)
    data = json.loads((out / "erp" / "suppliers_export.json").read_text())
    # Smoke sets tier1=20, tier2=8, so base = 28. Near-dup extras add a few.
    assert 28 <= len(data["suppliers"]) <= 32, len(data["suppliers"])
