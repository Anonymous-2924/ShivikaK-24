"""src.retrieve.service.answer_question: connection reuse + the real bug
this surfaced during Phase 6 eval (a Neo4j failure during entity
resolution was silently treated the same as 'entity not found', instead
of skipping structural dispatch outright)."""
from __future__ import annotations

from src.retrieve.service import QueryConfig, answer_question


class _FakeSession:
    def __init__(self, scripted, *, raise_on_resolve=False):
        self.scripted = scripted
        self.raise_on_resolve = raise_on_resolve
        self.calls = 0

    def run(self, cypher, **params):
        self.calls += 1
        if self.raise_on_resolve:
            raise RuntimeError("AuthenticationRateLimit (simulated)")
        for key, rows in self.scripted.items():
            if key in cypher:
                return rows
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeDriver:
    def __init__(self, scripted, *, raise_on_resolve=False):
        self.scripted = scripted
        self.raise_on_resolve = raise_on_resolve
        self.closed = False

    def session(self, database):
        return _FakeSession(self.scripted, raise_on_resolve=self.raise_on_resolve)

    def close(self):
        self.closed = True


def _cfg() -> QueryConfig:
    return QueryConfig(
        qdrant_url="http://x", qdrant_api_key=None,
        ollama_embed_host="http://x", ollama_embed_model="bge-m3",
        ollama_embed_dim=1024, neo4j_uri="bolt://x", neo4j_user="u",
        neo4j_password="p", top_k_semantic=20, hops_structural=3,
    )


def test_reused_driver_is_not_closed_by_answer_question():
    driver = _FakeDriver({"n.id = $q": [{"id": "SUP-1"}], "MATCH p =": []})
    answer_question("What depends on SUP-1?", cfg=_cfg(), driver=driver,
                     log_fn=lambda m: None)
    assert driver.closed is False


def test_neo4j_failure_during_resolution_skips_structural_dispatch_cleanly():
    """The bug: a transient Neo4j failure while resolving the entity hint
    must NOT be treated the same as 'no entity found' and fall through
    to calling exposure_paths with entity_id=None. It should skip
    structural dispatch outright and report zero confidence, not a
    false-negative 'entity not found' that masks an infra problem."""
    driver = _FakeDriver({}, raise_on_resolve=True)
    logs = []
    result = answer_question("What depends on SUP-1?", cfg=_cfg(),
                              driver=driver, log_fn=logs.append)
    assert result.graph_paths == []
    assert any("Neo4j unavailable" in m for m in logs)
    assert not any("no entity hint resolved" in m for m in logs)


def test_owned_driver_is_closed(monkeypatch):
    driver = _FakeDriver({"n.id = $q": [{"id": "SUP-1"}], "MATCH p =": []})
    monkeypatch.setattr("src.retrieve.service._init_neo4j", lambda cfg: driver)
    answer_question("What depends on SUP-1?", cfg=_cfg(), log_fn=lambda m: None)
    assert driver.closed is True
