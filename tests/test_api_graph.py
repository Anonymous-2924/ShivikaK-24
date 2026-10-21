"""GET /graph/stats and GET /entity/{id} against a fake Neo4j driver —
same fake-driver pattern as tests/test_graph_writer_stub.py."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import ApiConfig, create_app


class _FakeResult:
    """Mimics neo4j's Result: iterable (for ``for row in session.run(...)``)
    and ``.single()`` (for ``session.run(...).single()``)."""

    def __init__(self, rows: list, single_row) -> None:
        self.rows = rows
        self._single_row = single_row

    def __iter__(self):
        return iter(self.rows)

    def single(self):
        return self._single_row


class _FakeSession:
    """``scripted`` maps a cypher substring to (rows, single_row) — the
    endpoint under test uses one or the other, never both."""

    def __init__(self, scripted: dict) -> None:
        self.scripted = scripted

    def run(self, cypher, **params):
        for key, (rows, single_row) in self.scripted.items():
            if key in cypher:
                return _FakeResult(rows, single_row)
        return _FakeResult([], None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeDriver:
    def __init__(self, scripted: dict) -> None:
        self.scripted = scripted
        self.closed = False

    def session(self, database=None):
        return _FakeSession(self.scripted)

    def close(self):
        self.closed = True


def test_graph_stats_reachable(monkeypatch):
    driver = _FakeDriver({
        "MATCH (n)": ([{"label": "SKU", "n": 2}, {"label": "Supplier", "n": 1}], None),
        "MATCH ()-[r]->()": ([{"t": "contains", "n": 3}], None),
    })
    monkeypatch.setattr("src.api.app._neo4j_driver", lambda: driver)
    client = TestClient(create_app(ApiConfig()))
    res = client.get("/graph/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["reachable"] is True
    assert body["node_counts"] == {"SKU": 2, "Supplier": 1}
    assert body["edge_counts"] == {"contains": 3}
    assert driver.closed is True


def test_graph_stats_unreachable(monkeypatch):
    monkeypatch.setattr("src.api.app._neo4j_driver", lambda: None)
    client = TestClient(create_app(ApiConfig()))
    res = client.get("/graph/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["reachable"] is False
    assert body["node_counts"] == {}


def test_entity_found(monkeypatch):
    row = {"id": "SUP-1", "labels": ["Supplier"], "props": {"name": "Horizon"}}
    driver = _FakeDriver({"MATCH (n {id": ([], row)})
    monkeypatch.setattr("src.api.app._neo4j_driver", lambda: driver)
    client = TestClient(create_app(ApiConfig()))
    res = client.get("/entity/SUP-1")
    assert res.status_code == 200
    body = res.json()
    assert body == {"id": "SUP-1", "labels": ["Supplier"],
                     "properties": {"name": "Horizon"}}
    assert driver.closed is True


def test_entity_not_found(monkeypatch):
    driver = _FakeDriver({"MATCH (n {id": ([], None)})
    monkeypatch.setattr("src.api.app._neo4j_driver", lambda: driver)
    client = TestClient(create_app(ApiConfig()))
    res = client.get("/entity/NOPE")
    assert res.status_code == 404


def test_entity_neo4j_unreachable(monkeypatch):
    monkeypatch.setattr("src.api.app._neo4j_driver", lambda: None)
    client = TestClient(create_app(ApiConfig()))
    res = client.get("/entity/SUP-1")
    assert res.status_code == 503
