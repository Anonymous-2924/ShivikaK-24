"""SQLite-backed metadata, financial-fact and query-cache store.

Lightweight, file-based, no server required. Ingestion is idempotent: documents
are keyed by ``document_id`` (a content hash) so re-ingesting an unchanged file
updates in place rather than duplicating.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from src.ingestion.metadata import DocumentMetadata
from src.utils.errors import StorageError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    company_id TEXT,
    company_name TEXT NOT NULL,
    ticker TEXT,
    exchange TEXT,
    financial_year TEXT,
    period_start TEXT,
    period_end TEXT,
    document_type TEXT,
    report_type TEXT,
    basis TEXT,
    publication_date TEXT,
    source_url TEXT,
    source_filename TEXT,
    local_path TEXT,
    document_hash TEXT,
    file_size_bytes INTEGER,
    download_timestamp TEXT,
    parser_name TEXT,
    parser_version TEXT,
    parse_status TEXT,
    index_status TEXT,
    verification_status TEXT,
    warnings TEXT,
    ingestion_timestamp TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_company ON documents(company_name);
CREATE INDEX IF NOT EXISTS idx_docs_hash ON documents(document_hash);

CREATE TABLE IF NOT EXISTS financial_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    financial_year TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL,
    currency TEXT,
    units TEXT,
    basis TEXT,
    source_document_id TEXT,
    source_page INTEGER,
    source_table TEXT,
    source_note TEXT,
    extraction_method TEXT,
    verification_status TEXT,
    UNIQUE(company_name, financial_year, metric_name, basis)
);

CREATE TABLE IF NOT EXISTS query_cache (
    query_hash TEXT PRIMARY KEY,
    query TEXT,
    response TEXT,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS query_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT,
    created_at REAL
);
"""


class MetadataStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as exc:  # pragma: no cover - defensive
            conn.rollback()
            raise StorageError(str(exc)) from exc
        finally:
            conn.close()

    # ---- documents ------------------------------------------------------
    def upsert_document(self, doc: DocumentMetadata) -> None:
        d = doc.model_dump()
        d["document_type"] = doc.document_type.value
        d["basis"] = doc.basis.value
        d["parse_status"] = doc.parse_status.value
        d["index_status"] = doc.index_status.value
        d["verification_status"] = doc.verification_status.value
        d["warnings"] = json.dumps(doc.warnings)
        cols = list(d.keys())
        placeholders = ",".join(f":{c}" for c in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "document_id")
        sql = (
            f"INSERT INTO documents ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(document_id) DO UPDATE SET {updates}"
        )
        with self._conn() as c:
            c.execute(sql, d)

    def get_document(self, document_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM documents WHERE document_id=?", (document_id,)).fetchone()
        return _row_to_doc(row) if row else None

    def list_documents(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM documents ORDER BY ingestion_timestamp DESC").fetchall()
        return [_row_to_doc(r) for r in rows]

    def known_hashes(self) -> set[str]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT document_hash FROM documents WHERE document_hash IS NOT NULL"
            ).fetchall()
        return {r["document_hash"] for r in rows}

    def find_by_hash(self, file_hash: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM documents WHERE document_hash=?", (file_hash,)).fetchone()
        return _row_to_doc(row) if row else None

    def delete_document(self, document_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM documents WHERE document_id=?", (document_id,))
            c.execute("DELETE FROM financial_facts WHERE source_document_id=?", (document_id,))

    def companies(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute("SELECT DISTINCT company_name FROM documents ORDER BY company_name").fetchall()
        return [r["company_name"] for r in rows]

    def stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"]
            companies = c.execute("SELECT COUNT(DISTINCT company_name) n FROM documents").fetchone()["n"]
            years = c.execute(
                "SELECT COUNT(DISTINCT financial_year) n FROM documents WHERE financial_year IS NOT NULL"
            ).fetchone()["n"]
            indexed = c.execute("SELECT COUNT(*) n FROM documents WHERE index_status='indexed'").fetchone()["n"]
            failed = c.execute(
                "SELECT COUNT(*) n FROM documents WHERE parse_status='failed' OR index_status='failed'"
            ).fetchone()["n"]
        return {
            "documents": total,
            "companies": companies,
            "financial_years": years,
            "indexed": indexed,
            "failed": failed,
        }

    # ---- financial facts ------------------------------------------------
    def upsert_fact(self, fact) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO financial_facts
                   (company_name, financial_year, metric_name, value, currency, units, basis,
                    source_document_id, source_page, source_table, source_note,
                    extraction_method, verification_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(company_name, financial_year, metric_name, basis)
                   DO UPDATE SET value=excluded.value, currency=excluded.currency,
                     units=excluded.units, source_document_id=excluded.source_document_id,
                     source_page=excluded.source_page, source_table=excluded.source_table,
                     source_note=excluded.source_note, extraction_method=excluded.extraction_method,
                     verification_status=excluded.verification_status""",
                (fact.company_name, fact.financial_year, fact.metric_name, fact.value,
                 fact.currency, fact.units, fact.basis, fact.source_document_id, fact.source_page,
                 fact.source_table, fact.source_note, fact.extraction_method, fact.verification_status),
            )

    def get_facts(self, company_name: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM financial_facts WHERE lower(company_name)=lower(?)", (company_name,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- query cache / log ----------------------------------------------
    def cache_get(self, query_hash: str, max_age_s: float = 86400) -> Optional[str]:
        with self._conn() as c:
            row = c.execute("SELECT response, created_at FROM query_cache WHERE query_hash=?",
                            (query_hash,)).fetchone()
        if not row:
            return None
        if time.time() - row["created_at"] > max_age_s:
            return None
        return row["response"]

    def cache_put(self, query_hash: str, query: str, response: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO query_cache (query_hash, query, response, created_at) "
                "VALUES (?,?,?,?)", (query_hash, query, response, time.time()))

    def log_query(self, query: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO query_log (query, created_at) VALUES (?,?)", (query, time.time()))

    def recent_queries(self, limit: int = 10) -> list[str]:
        with self._conn() as c:
            rows = c.execute("SELECT query FROM query_log ORDER BY created_at DESC LIMIT ?",
                             (limit,)).fetchall()
        return [r["query"] for r in rows]


def _row_to_doc(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("warnings"):
        try:
            d["warnings"] = json.loads(d["warnings"])
        except (json.JSONDecodeError, TypeError):
            d["warnings"] = []
    else:
        d["warnings"] = []
    return d
