"""Structural dispatcher against a fake Neo4j driver (same pattern as
test_graph_writer_stub.py) — no real Neo4j required."""
from __future__ import annotations

from src.retrieve.structural import exposure_paths, find_entity_id


class _FakeSession:
    def __init__(self, scripted: dict[str, list[dict]]):
        self.scripted = scripted
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        for key, rows in self.scripted.items():
            if key in cypher:
                return rows
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeDriver:
    def __init__(self, scripted: dict[str, list[dict]]):
        self.scripted = scripted
        self.sessions: list[_FakeSession] = []

    def session(self, database: str):
        s = _FakeSession(self.scripted)
        self.sessions.append(s)
        return s


def test_find_entity_id_exact_id_match():
    driver = _FakeDriver({"n.id = $q": [{"id": "SUP-0001"}]})
    eid = find_entity_id(driver, "SUP-0001")
    assert eid == "SUP-0001"


def test_find_entity_id_falls_back_to_name_substring():
    driver = _FakeDriver({
        "n.id = $q": [],
        "CONTAINS toLower($q)": [{"id": "SUP-0042"}],
    })
    eid = find_entity_id(driver, "Horizon")
    assert eid == "SUP-0042"


def test_find_entity_id_returns_none_when_nothing_matches():
    driver = _FakeDriver({"n.id = $q": [], "CONTAINS toLower($q)": []})
    assert find_entity_id(driver, "nope") is None


def test_exposure_paths_returns_structured_records():
    row = {
        "target_id": "SKU-100", "target_type": "SKU", "hops": 2,
        "path_nodes": [{"id": "SUP-1", "labels": ["Supplier"]},
                       {"id": "SKU-100", "labels": ["SKU"]}],
        "path_rels": [{"type": "supplied_by", "confidence": 0.9,
                        "extraction_method": "structured",
                        "source_ref": {"doc_id": "x.json"},
                        "valid_from": "2026-01-01", "valid_to": None}],
    }
    driver = _FakeDriver({"MATCH p =": [row]})
    paths = exposure_paths(driver, "SUP-1", max_hops=3)
    assert len(paths) == 1
    assert paths[0].target_id == "SKU-100"
    assert paths[0].target_type == "SKU"
    assert paths[0].hops == 2
    assert paths[0].path_rels[0]["type"] == "supplied_by"


def test_exposure_paths_embeds_hop_count_in_cypher_not_as_param():
    driver = _FakeDriver({"MATCH p =": []})
    exposure_paths(driver, "SUP-1", max_hops=4)
    session = driver.sessions[0]
    cypher, params = session.calls[0]
    assert "*1..4" in cypher
    assert "hops" not in params


def test_exposure_paths_adds_temporal_filter_when_as_of_given():
    driver = _FakeDriver({"MATCH p =": []})
    exposure_paths(driver, "SUP-1", as_of="2026-03-01")
    cypher, params = driver.sessions[0].calls[0]
    assert "valid_from" in cypher
    assert params["as_of"] == "2026-03-01"


def test_exposure_paths_rejects_nonpositive_hops():
    driver = _FakeDriver({})
    try:
        exposure_paths(driver, "SUP-1", max_hops=0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
