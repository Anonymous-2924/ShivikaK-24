"""Audit log round-trips and skip-already-succeeded behaviour."""
from __future__ import annotations

from pathlib import Path

from src.ingest.audit import AuditLog


def test_audit_roundtrip_and_already_succeeded(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.sqlite")
    with log.record(file="a.pdf", sha256="abc", track="narrative",
                     extractor="pdfplumber") as rec:
        rec.done(confidence=0.9, rows_or_chars=100)
    assert log.already_succeeded("a.pdf", "abc") is True
    assert log.already_succeeded("a.pdf", "DIFFERENT_HASH") is False

    s = log.summary()
    assert s.get("narrative:ok") == 1


def test_audit_records_failure_and_does_not_mark_success(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.sqlite")
    try:
        with log.record(file="broken.pdf", sha256="xyz",
                         track="narrative", extractor="pdfplumber"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert log.already_succeeded("broken.pdf", "xyz") is False
    s = log.summary()
    assert s.get("narrative:fail") == 1
