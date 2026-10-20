"""Regression test for a real bug caught running build-graph against an
actual Neo4j server for the first time (Phase 6): Cypher property values
can only be a primitive or an array of primitives, never a nested map.
``source_ref`` (a dict) made every single edge write raise
CypherTypeError. The existing fake-driver tests in
test_graph_writer_stub.py never caught this because the fake driver just
logs whatever it's given — it doesn't enforce Neo4j's actual property
type rules. This test asserts the writer itself never hands the driver
anything but JSON-safe values.
"""
from __future__ import annotations

import json
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


def _writer_with_fake_driver(monkeypatch):
    from src.graph import writer as _w

    fake = _Driver()

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            return fake

    import neo4j
    monkeypatch.setattr(neo4j, "GraphDatabase", FakeGraphDatabase)
    w = _w.Neo4jWriter(uri="bolt://fake", user="u", password="p")
    return w, fake


def _assert_all_props_primitive_or_primitive_array(props: dict) -> None:
    primitive = (str, int, float, bool, type(None))
    for k, v in props.items():
        if isinstance(v, primitive):
            continue
        if isinstance(v, list) and all(isinstance(x, primitive) for x in v):
            continue
        raise AssertionError(
            f"property {k!r}={v!r} is not Neo4j-safe (not a primitive or "
            f"an array of primitives) — this is exactly what crashed "
            f"against a real server"
        )


def test_upsert_edges_never_sends_a_nested_dict_property(monkeypatch) -> None:
    from src.graph.writer import Edge, Node

    w, fake = _writer_with_fake_driver(monkeypatch)
    w.upsert_nodes([
        Node(type="Supplier", id="SUP-1", props={"name": "Horizon"}),
        Node(type="Geography", id="GEO-BD", props={}),
    ])
    edge = Edge(
        source_type="Supplier", source_id="SUP-1",
        target_type="Geography", target_id="GEO-BD",
        rel_type="located_in",
        props={
            "confidence": 0.95, "valid_from": "2026-01-01",
            "valid_to": None,
            # This nested dict is what Neo4j rejected with CypherTypeError.
            "source_ref": {"doc_id": "x.json", "chunk_index": 3},
            "extraction_method": "structured",
        },
    )
    written, rejected = w.upsert_edges([edge])
    assert written == 1 and rejected == 0

    edge_calls = [kw for cypher, kw in fake.log if "MERGE (a)-[r:" in cypher]
    assert len(edge_calls) == 1
    sent_props = edge_calls[0]["props"]
    _assert_all_props_primitive_or_primitive_array(sent_props)
    # And it must round-trip losslessly as JSON.
    assert json.loads(sent_props["source_ref"]) == {
        "doc_id": "x.json", "chunk_index": 3,
    }


def test_upsert_nodes_also_sanitises_nested_props(monkeypatch) -> None:
    from src.graph.writer import Node

    w, fake = _writer_with_fake_driver(monkeypatch)
    w.upsert_nodes([Node(type="DataTable", id="TBL-1", props={
        "parquet_path": "/x.parquet",
        "nested": {"a": 1},
    })])
    node_calls = [kw for cypher, kw in fake.log if "MERGE (n:" in cypher]
    _assert_all_props_primitive_or_primitive_array(node_calls[0]["props"])


def test_validate_edge_still_runs_against_the_original_dict(monkeypatch) -> None:
    """Sanitisation must happen AFTER schema validation, on a copy — the
    validator (src.graph.schema.validate_edge) still needs the real dict
    shape, e.g. to check source_ref has a 'doc_id' key."""
    from src.graph.writer import Edge, Node

    w, fake = _writer_with_fake_driver(monkeypatch)
    w.upsert_nodes([
        Node(type="Supplier", id="SUP-1", props={}),
        Node(type="Geography", id="GEO-BD", props={}),
    ])
    bad_edge = Edge(
        source_type="Supplier", source_id="SUP-1",
        target_type="Geography", target_id="GEO-BD",
        rel_type="located_in",
        props={
            "confidence": 0.95, "valid_from": "2026-01-01",
            "valid_to": None,
            "source_ref": {"not_doc_id": "oops"},   # missing required doc_id
            "extraction_method": "structured",
        },
    )
    written, rejected = w.upsert_edges([bad_edge])
    assert written == 0 and rejected == 1
