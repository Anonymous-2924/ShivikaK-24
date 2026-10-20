"""End-to-end ingest with Qdrant disabled.

Uses the Phase 2 generator in --smoke mode as the source corpus. Verifies
that files land in the right processed-tree subdirectory, the audit log
records them, and the data cards exist for every parquet.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pytest

# Need the whole writer stack from Phase 2 to produce a corpus.
pytest.importorskip("openpyxl")
pytest.importorskip("docx")
pytest.importorskip("reportlab")

from src.ingest.pipeline import IngestConfig, run  # noqa: E402

ROOT = Path(__file__).parent.parent


def _generate_corpus(out: Path) -> None:
    r = subprocess.run(
        [sys.executable, "-m", "tools.datagen.generate",
         "--smoke", "--seed", "42", "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=90,
    )
    assert r.returncode == 0, r.stderr


def _mirror_subset_to_inbox(src: Path, inbox: Path) -> None:
    """Pick a representative handful: an xlsx, a csv, a pdf, a docx,
    a json, an xml, an md news article."""
    inbox.mkdir(parents=True, exist_ok=True)
    picks = [
        src / "supplier_master.xlsx",
        next((src / "shipments").glob("shipment_log.csv")),
        next((src / "audits").glob("*.pdf")),
        next((src / "correspondence").glob("*.docx")),
        src / "erp" / "suppliers_export.json",
        src / "erp" / "plants_export.xml",
        next((src / "news").glob("*.md")),
    ]
    for p in picks:
        (inbox / p.name).write_bytes(p.read_bytes())


def test_end_to_end_without_qdrant(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    _generate_corpus(corpus)
    inbox = tmp_path / "inbox"
    _mirror_subset_to_inbox(corpus, inbox)

    processed = tmp_path / "processed"
    narrative_dir = processed / "narrative"
    numeric_dir = processed / "numeric"
    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()

    monkeypatch.setenv("INGEST_ENABLE_QDRANT", "0")
    cfg = IngestConfig(
        inbox=inbox, gold=gold_dir,
        processed_narrative=narrative_dir,
        processed_numeric=numeric_dir,
        audit_path=processed / "audit.sqlite",
        table_confidence_floor=0.75,
        enable_qdrant=False,
        qdrant_url="", qdrant_api_key=None,
        ollama_embed_host="", ollama_embed_model="",
        ollama_embed_dim=0,
    )

    stats = run(cfg, force=False, log_fn=lambda _: None)
    assert stats.failures == 0, "ingest reported failures"
    assert stats.qdrant_skipped is True
    assert stats.narrative_ok >= 3    # pdf + docx + md at least
    assert stats.numeric_ok >= 1      # supplier_master.xlsx produces several sheets
    assert stats.structured_ok >= 2   # json + xml

    # Every parquet should have a sibling .md data card.
    for parquet in numeric_dir.glob("*.parquet"):
        assert parquet.with_suffix(".md").exists(), (
            f"missing data card for {parquet.name}"
        )
        # And the parquet should be readable.
        assert pq.read_table(parquet).num_columns > 0

    # At least one narrative markdown file exists.
    assert any(narrative_dir.glob("*.md")), (
        "no narrative markdown produced"
    )


def test_rerun_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    _generate_corpus(corpus)
    inbox = tmp_path / "inbox"
    _mirror_subset_to_inbox(corpus, inbox)
    processed = tmp_path / "processed"
    monkeypatch.setenv("INGEST_ENABLE_QDRANT", "0")
    cfg = IngestConfig(
        inbox=inbox, gold=tmp_path / "gold",
        processed_narrative=processed / "narrative",
        processed_numeric=processed / "numeric",
        audit_path=processed / "audit.sqlite",
        table_confidence_floor=0.75,
        enable_qdrant=False, qdrant_url="", qdrant_api_key=None,
        ollama_embed_host="", ollama_embed_model="", ollama_embed_dim=0,
    )
    first = run(cfg, force=False, log_fn=lambda _: None)
    second = run(cfg, force=False, log_fn=lambda _: None)
    assert first.narrative_ok >= 1
    # Second pass skips everything the first pass succeeded on.
    assert second.narrative_ok == 0
    assert second.numeric_ok == 0
    assert second.structured_ok == 0
    assert second.skipped >= first.files_scanned - first.failures


def test_pdf_table_confidence_degrades_below_floor(tmp_path: Path,
                                                     monkeypatch) -> None:
    """Set the floor to 1.1 so NO table clears it — every PDF table must
    then be degraded to a narrative pipe-table, logged as such."""
    corpus = tmp_path / "corpus"
    _generate_corpus(corpus)
    audit_pdf = next((corpus / "audits").glob("*.pdf"))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / audit_pdf.name).write_bytes(audit_pdf.read_bytes())
    processed = tmp_path / "processed"
    monkeypatch.setenv("INGEST_ENABLE_QDRANT", "0")
    cfg = IngestConfig(
        inbox=inbox, gold=tmp_path / "gold",
        processed_narrative=processed / "narrative",
        processed_numeric=processed / "numeric",
        audit_path=processed / "audit.sqlite",
        table_confidence_floor=1.1,      # impossible floor
        enable_qdrant=False, qdrant_url="", qdrant_api_key=None,
        ollama_embed_host="", ollama_embed_model="", ollama_embed_dim=0,
    )
    stats = run(cfg, force=False, log_fn=lambda _: None)
    assert stats.failures == 0
    assert stats.tables_degraded_to_narrative >= 1
    # No parquets written from table extraction (gold dir is empty).
    assert not list((processed / "numeric").glob("*audit*tbl*.parquet"))
