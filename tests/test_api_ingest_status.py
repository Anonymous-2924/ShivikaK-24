"""GET /ingest/status against a real temp SQLite audit log (fast, no
mocking needed — same DDL as src/ingest/audit.py)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import ApiConfig, create_app
from src.ingest.audit import DDL


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    conn.execute(
        "INSERT INTO extractions (file, file_sha256, track, extractor, "
        "confidence, started_at, ended_at, ok, note, rows_or_chars) "
        "VALUES ('a.pdf','sha1','narrative','pdfplumber',0.9,'t0','t1',1,NULL,100)"
    )
    conn.execute(
        "INSERT INTO extractions (file, file_sha256, track, extractor, "
        "confidence, started_at, ended_at, ok, note, rows_or_chars) "
        "VALUES ('b.xlsx','sha2','numeric','openpyxl',1.0,'t2','t3',1,NULL,50)"
    )
    conn.commit()
    conn.close()


def test_ingest_status_with_real_db(tmp_path: Path):
    db_path = tmp_path / "audit.sqlite"
    _make_db(db_path)
    cfg = ApiConfig(audit_db_path=db_path)
    client = TestClient(create_app(cfg))
    res = client.get("/ingest/status")
    assert res.status_code == 200
    body = res.json()
    assert body["audit_db_found"] is True
    assert body["total_rows"] == 2
    assert body["by_track_and_outcome"] == {"narrative:ok": 1, "numeric:ok": 1}
    assert body["last_run_at"] == "t3"


def test_ingest_status_missing_db(tmp_path: Path):
    cfg = ApiConfig(audit_db_path=tmp_path / "does_not_exist.sqlite")
    client = TestClient(create_app(cfg))
    res = client.get("/ingest/status")
    assert res.status_code == 200
    body = res.json()
    assert body["audit_db_found"] is False
    assert body["total_rows"] == 0
