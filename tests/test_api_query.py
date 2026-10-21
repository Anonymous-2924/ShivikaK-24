"""POST /query with a mocked router/retrieval service — no real
Neo4j/Qdrant/Ollama needed."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import ApiConfig, create_app
from src.retrieve.combine import AnswerObject, SourceRef
from src.retrieve.quantitative import QuantResult
from src.retrieve.semantic import SemanticHit
from src.retrieve.structural import PathRecord


def _stub_answer_question(question, *, as_of=None, log_fn=print):
    return AnswerObject(
        question=question, categories=["structural"],
        direct_answer="2 SKU(s) reachable: SKU-1, SKU-2",
        supporting_chunks=[SemanticHit(
            doc_id="a.md::chunk::0", kind="chunk", text="hello",
            source_file="a.md", score=0.9, confidence=0.9,
            extraction_method="structured",
        )],
        graph_paths=[PathRecord(
            target_id="SKU-1", target_type="SKU", hops=1,
            path_nodes=[{"id": "SUP-1", "labels": ["Supplier"]}],
            path_rels=[{"type": "supplied_by", "confidence": 0.98}],
        )],
        quantitative=[QuantResult(
            metric="revenue", parquet_path="/d/x.parquet",
            column_used="revenue_usd", result={"total": 100.0},
            note="matched",
        )],
        confidence=0.9, as_of=as_of,
        source_refs=[SourceRef(doc_id="a.md", kind="narrative", detail={})],
    )


def test_query_returns_shaped_response(monkeypatch):
    monkeypatch.setattr(
        "src.retrieve.service.answer_question", _stub_answer_question)
    client = TestClient(create_app(ApiConfig()))
    res = client.post("/query", json={"question": "What depends on SUP-1?"})
    assert res.status_code == 200
    body = res.json()
    assert body["question"] == "What depends on SUP-1?"
    assert body["categories"] == ["structural"]
    assert body["confidence"] == 0.9
    assert body["source_refs"] == [{"doc_id": "a.md", "kind": "narrative", "detail": {}}]
    assert body["graph_paths"][0]["target_id"] == "SKU-1"
    assert body["quantitative"][0]["result"] == {"total": 100.0}
    assert body["supporting_chunks"][0]["doc_id"] == "a.md::chunk::0"


def test_query_passes_as_of_through(monkeypatch):
    seen = {}

    def _capture(question, *, as_of=None, log_fn=print):
        seen["as_of"] = as_of
        return _stub_answer_question(question, as_of=as_of, log_fn=log_fn)

    monkeypatch.setattr("src.retrieve.service.answer_question", _capture)
    client = TestClient(create_app(ApiConfig()))
    client.post("/query", json={"question": "q", "as_of": "2026-01-01"})
    assert seen["as_of"] == "2026-01-01"


def test_query_timeout_returns_504(monkeypatch):
    import time

    def _slow(question, *, as_of=None, log_fn=print):
        time.sleep(0.2)
        return _stub_answer_question(question, as_of=as_of, log_fn=log_fn)

    monkeypatch.setattr("src.retrieve.service.answer_question", _slow)
    client = TestClient(create_app(ApiConfig(max_query_timeout_s=0.01)))
    res = client.post("/query", json={"question": "q"})
    assert res.status_code == 504
