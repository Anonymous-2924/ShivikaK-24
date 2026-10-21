"""Graph writer with a mock neo4j driver. Verifies schema rejection and
upsert MERGE call shape without needing a real Neo4j server.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any


class _Session:
    def __init__(self, log: list) -> None:
        self.log = log

    def run(self, cypher: str, **kw: Any) -> None:
        self.log.append((cypher.strip(), kw))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Driver:
    def __init__(self) -> None:
        self.log: list = []

    @contextmanager
    def session(self, database: str):
        yield _Session(self.log)

    def close(self) -> None:
        pass


def _writer_with_fake_driver(monkeypatch) -> tuple[object, _Driver]:
    """Construct Neo4jWriter without connecting; swap in the fake driver."""
    from src.graph import writer as _w

    fake = _Driver()

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            return fake

    # Patch the import inside Neo4jWriter.__init__.
    import neo4j
    monkeypatch.setattr(neo4j, "GraphDatabase", FakeGraphDatabase)
    w = _w.Neo4jWriter(uri="bolt://fake", user="u", password="p")
    return w, fake


def test_writer_rejects_invalid_triple(monkeypatch) -> None:
    from src.graph.writer import Edge, Node

    w, fake = _writer_with_fake_driver(monkeypatch)
    w.upsert_nodes([
        Node(type="Geography", id="GEO-BD", props={"name": "Bangladesh"}),
        Node(type="SKU",       id="SKU-1",  props={}),
    ])
    # Intentionally invalid: Geography cannot be supplied_by SKU.
    bad = Edge(
        source_type="Geography", source_id="GEO-BD",
        target_type="SKU", target_id="SKU-1",
        rel_type="supplied_by",
        props={
            "confidence": 0.9, "valid_from": "2026-01-01",
            "valid_to": None, "source_ref": {"doc_id": "x.md"},
            "extraction_method": "llm_extracted",
        },
    )
    written, rejected = w.upsert_edges([bad])
    assert written == 0 and rejected == 1
    # Node upserts hit the driver; the rejected edge did NOT.
    cyphers = [c for c, _ in fake.log]
    assert any("MERGE (n:Geography" in c for c in cyphers)
    assert any("MERGE (n:SKU" in c for c in cyphers)
    assert not any("MERGE (a)-[r:supplied_by" in c for c in cyphers)


def test_writer_writes_valid_edge(monkeypatch) -> None:
    from src.graph.writer import Edge, Node

    w, fake = _writer_with_fake_driver(monkeypatch)
    w.upsert_nodes([
        Node(type="Supplier",  id="SUP-1",  props={"name": "Horizon"}),
        Node(type="Geography", id="GEO-BD", props={}),
    ])
    good = Edge(
        source_type="Supplier", source_id="SUP-1",
        target_type="Geography", target_id="GEO-BD",
        rel_type="located_in",
        props={
            "confidence": 0.95, "valid_from": "2026-01-01",
            "valid_to": None, "source_ref": {"doc_id": "x.json"},
            "extraction_method": "structured",
        },
    )
    written, rejected = w.upsert_edges([good])
    assert written == 1 and rejected == 0
    cyphers = [c for c, _ in fake.log]
    assert any("MERGE (a)-[r:located_in" in c for c in cyphers)
