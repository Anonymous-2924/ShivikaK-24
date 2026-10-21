"""SQLite audit log for every ingest extraction.

One row per (file, extractor) attempt. Rerunning the ingest consults this
table to skip files that already succeeded. Also the ground-truth record
for Phase 6 to compare against REALISM_LOG.md.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS extractions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file            TEXT    NOT NULL,
    file_sha256     TEXT    NOT NULL,
    -- track: narrative | numeric | structured | image | gold | skipped
    track           TEXT    NOT NULL,
    -- extractor: pdfplumber | camelot | pdfplumber+camelot | openpyxl |
    --           csv | json | xml | docx | plaintext | gold
    extractor       TEXT    NOT NULL,
    confidence      REAL    NOT NULL,          -- 0..1
    started_at      TEXT    NOT NULL,
    ended_at        TEXT    NOT NULL,
    ok              INTEGER NOT NULL,          -- 0/1
    note            TEXT,
    -- rows written (numeric) or chars emitted (narrative)
    rows_or_chars   INTEGER
);
CREATE INDEX IF NOT EXISTS ix_extractions_file ON extractions(file);
CREATE INDEX IF NOT EXISTS ix_extractions_ok   ON extractions(ok);
"""


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(DDL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def record(self, *, file: str, sha256: str, track: str,
               extractor: str) -> Iterator[ExtractionRecord]:
        """Context manager — timestamps start/end around the body and
        inserts one row on exit, success or failure."""
        rec = ExtractionRecord(file=file, sha256=sha256, track=track,
                               extractor=extractor,
                               started_at=_now())
        try:
            yield rec
        except Exception as exc:   # noqa: BLE001
            rec.ok = False
            rec.note = f"{type(exc).__name__}: {exc}"[:500]
            rec.ended_at = _now()
            self._insert(rec)
            raise
        else:
            if rec.ended_at is None:
                rec.ended_at = _now()
            self._insert(rec)

    def _insert(self, r: ExtractionRecord) -> None:
        self._conn.execute(
            "INSERT INTO extractions "
            "(file, file_sha256, track, extractor, confidence, started_at, "
            " ended_at, ok, note, rows_or_chars) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r.file, r.sha256, r.track, r.extractor, r.confidence,
             r.started_at, r.ended_at, int(bool(r.ok)), r.note,
             r.rows_or_chars),
        )
        self._conn.commit()

    def already_succeeded(self, file: str, sha256: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM extractions "
            "WHERE file = ? AND file_sha256 = ? AND ok = 1 LIMIT 1",
            (file, sha256),
        )
        return cur.fetchone() is not None

    def summary(self) -> dict[str, int]:
        cur = self._conn.execute(
            "SELECT track, ok, COUNT(*) AS n FROM extractions GROUP BY track, ok"
        )
        out: dict[str, int] = {}
        for row in cur:
            key = f"{row['track']}:{'ok' if row['ok'] else 'fail'}"
            out[key] = row["n"]
        return out


class ExtractionRecord:
    __slots__ = ("file", "sha256", "track", "extractor", "confidence",
                 "started_at", "ended_at", "ok", "note", "rows_or_chars")

    def __init__(self, *, file: str, sha256: str, track: str,
                 extractor: str, started_at: str) -> None:
        self.file = file
        self.sha256 = sha256
        self.track = track
        self.extractor = extractor
        self.confidence = 0.0
        self.started_at = started_at
        self.ended_at: str | None = None
        self.ok = True
        self.note: str | None = None
        self.rows_or_chars: int | None = None

    def done(self, confidence: float, *,
             rows_or_chars: int | None = None,
             note: str | None = None) -> None:
        self.confidence = float(confidence)
        self.rows_or_chars = rows_or_chars
        self.note = note
        self.ended_at = _now()


def _now() -> str:
    return (dt.datetime.now(dt.UTC).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"))
