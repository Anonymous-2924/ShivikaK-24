"""Semantic dispatcher against mock Embedder / QdrantIndex."""
from __future__ import annotations

from src.retrieve.semantic import semantic_search


class _FakeEmbedder:
    def __init__(self):
        self.calls: list[str] = []

    def embed_one(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1, 0.2, 0.3]


class _FakeIndex:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.last_call: dict | None = None

    def search(self, vector, *, top_k=20, kind=None):
        self.last_call = {"vector": vector, "top_k": top_k, "kind": kind}
        return self.rows


def test_semantic_search_embeds_question_and_returns_hits():
    embedder = _FakeEmbedder()
    index = _FakeIndex([
        {"doc_id": "a.md::chunk::0", "kind": "chunk", "text": "hello",
         "source_file": "a.md", "score": 0.91, "confidence": 0.9,
         "extraction_method": "structured"},
    ])
    hits = semantic_search("what happened at ACME?", embedder=embedder, index=index)
    assert embedder.calls == ["what happened at ACME?"]
    assert index.last_call == {"vector": [0.1, 0.2, 0.3], "top_k": 20, "kind": "chunk"}
    assert len(hits) == 1
    assert hits[0].doc_id == "a.md::chunk::0"
    assert hits[0].score == 0.91
    assert hits[0].confidence == 0.9


def test_semantic_search_respects_top_k_and_kind():
    embedder = _FakeEmbedder()
    index = _FakeIndex([])
    semantic_search("q", embedder=embedder, index=index, top_k=5, kind="data_card")
    assert index.last_call == {"vector": [0.1, 0.2, 0.3], "top_k": 5, "kind": "data_card"}


def test_semantic_search_defaults_missing_payload_fields():
    embedder = _FakeEmbedder()
    index = _FakeIndex([{"doc_id": "x", "kind": "chunk", "score": 0.5}])
    hits = semantic_search("q", embedder=embedder, index=index)
    assert hits[0].text == ""
    assert hits[0].source_file == ""
    assert hits[0].confidence == 0.0
    assert hits[0].extraction_method == "unknown"
