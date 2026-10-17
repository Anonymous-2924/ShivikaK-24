"""Lightweight chunk repository (SQLite).

Stores chunk text + metadata so BM25 keyword retrieval and citation rendering
have a durable source of truth alongside the Qdrant vectors. Keyed by
``chunk_id`` for idempotent re-indexing.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
"""


class ChunkRepository:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_many(self, records: list[tuple[str, str, str, dict]]) -> None:
        """records: (chunk_id, document_id, text, metadata_dict)."""
        with self._conn() as c:
            c.executemany(
                "INSERT INTO chunks (chunk_id, document_id, text, metadata) VALUES (?,?,?,?) "
                "ON CONFLICT(chunk_id) DO UPDATE SET text=excluded.text, metadata=excluded.metadata",
                [(cid, did, text, json.dumps(meta)) for cid, did, text, meta in records],
            )

    def delete_document(self, document_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))

    def count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) n FROM chunks").fetchone()["n"]

    def document_chunk_ids(self, document_id: str) -> set[str]:
        with self._conn() as c:
            rows = c.execute("SELECT chunk_id FROM chunks WHERE document_id=?", (document_id,)).fetchall()
        return {r["chunk_id"] for r in rows}

    def all_chunks(self) -> list[tuple[str, str, dict]]:
        """Return (chunk_id, text, metadata) for every chunk (for BM25)."""
        with self._conn() as c:
            rows = c.execute("SELECT chunk_id, text, metadata FROM chunks").fetchall()
        return [(r["chunk_id"], r["text"], json.loads(r["metadata"])) for r in rows]

    def get_texts(self, chunk_ids: list[str]) -> dict[str, tuple[str, dict]]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" * len(chunk_ids))
        with self._conn() as c:
            rows = c.execute(
                f"SELECT chunk_id, text, metadata FROM chunks WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            ).fetchall()
        return {r["chunk_id"]: (r["text"], json.loads(r["metadata"])) for r in rows}
