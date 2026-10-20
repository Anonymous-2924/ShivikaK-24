"""Index wiring: with Qdrant+Ollama stubs, confirm the pipeline builds the
right IndexDoc stream and the Embedder+QdrantIndex are called with the
right shapes. Exercises code paths that the --no-qdrant tests skip.

This is an integration-shape test, not a round-trip test against a real
Qdrant server. The real server is tested manually by running the ingest
locally with docker compose up.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.index.qdrant import IndexDoc, _point_id


class _StubEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def ping(self) -> int:
        return 8

    def dim(self) -> int:
        return 8

    def embed_many(self, texts):
        self.calls.append(list(texts))
        # Deterministic fake vectors so we can assert on them.
        return [[float(i) / 8.0] * 8 for i, _ in enumerate(texts)]


class _StubQdrantIndex:
    def __init__(self) -> None:
        self.upserts: list[list[IndexDoc]] = []
        self.vectors_seen: list[list[list[float]]] = []
        self.ensure_called = False

    def ensure_collection(self) -> None:
        self.ensure_called = True

    def upsert(self, docs, vectors):
        self.upserts.append(list(docs))
        self.vectors_seen.append([list(v) for v in vectors])


def test_point_id_is_deterministic_uuid() -> None:
    a = _point_id("foo.pdf::chunk::0")
    b = _point_id("foo.pdf::chunk::0")
    c = _point_id("foo.pdf::chunk::1")
    assert a == b
    assert a != c
    # UUID shape (36 chars, hyphens at the right spots)
    assert len(a) == 36 and a[8] == "-" and a[13] == "-"


def test_pipeline_builds_indexdocs_and_calls_upsert(tmp_path: Path,
                                                      monkeypatch) -> None:
    from src.ingest import pipeline

    # Minimal real inbox: one json (structured track) and one md (narrative).
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "small.json").write_text(json.dumps({
        "export_from": "X",
        "widgets": [
            {"id": "W1", "qty": 1, "color": "red"},
            {"id": "W2", "qty": 2, "color": "blue"},
        ],
    }))
    (inbox / "note.md").write_text("# Note\n\nAlpha. Beta. Gamma delta.\n")

    processed = tmp_path / "processed"
    stub_emb = _StubEmbedder()
    stub_idx = _StubQdrantIndex()

    def fake_init_index(cfg, log_fn):
        return stub_idx, stub_emb

    monkeypatch.setattr(pipeline, "_init_index", fake_init_index)
    monkeypatch.setenv("INGEST_ENABLE_QDRANT", "1")

    cfg = pipeline.IngestConfig(
        inbox=inbox, gold=tmp_path / "gold",
        processed_narrative=processed / "narrative",
        processed_numeric=processed / "numeric",
        audit_path=processed / "audit.sqlite",
        table_confidence_floor=0.75,
        enable_qdrant=True,
        qdrant_url="http://stub", qdrant_api_key=None,
        ollama_embed_host="http://stub",
        ollama_embed_model="stub", ollama_embed_dim=8,
    )
    stats = pipeline.run(cfg, force=False, log_fn=lambda _: None)
    assert stats.failures == 0
    assert stats.narrative_ok >= 1
    assert stats.structured_ok >= 1
    assert stats.qdrant_skipped is False

    assert stub_idx.upserts, "pipeline never called QdrantIndex.upsert"
    all_docs = [d for batch in stub_idx.upserts for d in batch]
    kinds = {d.kind for d in all_docs}
    assert "chunk" in kinds, "no narrative chunks indexed"
    assert "data_card" in kinds, "no data card indexed"
    # Each chunk's payload-extra has char_start/char_end; each data card
    # points at a parquet.
    for d in all_docs:
        if d.kind == "chunk":
            assert "char_start" in d.extra_payload
            assert "char_end" in d.extra_payload
        elif d.kind == "data_card":
            assert d.extra_payload.get("parquet_path", "").endswith(".parquet")
    # Vector shape matches configured dim.
    first_vec = stub_idx.vectors_seen[0][0]
    assert len(first_vec) == 8
