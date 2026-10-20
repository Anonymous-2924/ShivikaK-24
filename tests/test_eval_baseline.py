"""Vector-RAG baseline against a stub Embedder/QdrantIndex/chat client —
no real Qdrant or Ollama needed, same test-double pattern as
tests/test_retrieve_semantic.py."""
from __future__ import annotations

from eval.baseline_vector_rag import answer_with_vector_rag


class _FakeEmbedder:
    def embed_one(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _FakeIndex:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def search(self, vector, *, top_k=20, kind=None):
        return self.rows


class _StubResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubChat:
    model = "gpt-oss:20b"

    def __init__(self, text: str, *, raises: Exception | None = None) -> None:
        self.text = text
        self.raises = raises

    def chat_text(self, *, system: str, user: str):
        if self.raises is not None:
            raise self.raises
        return _StubResponse(self.text)


_CANNED_CORPUS = [
    {"doc_id": "audit_SUP-T1-0022.pdf::chunk::0", "kind": "chunk",
     "text": "Subcontractor list missing one tier-2 fabric mill.",
     "source_file": "audit_SUP-T1-0022.pdf", "score": 0.88},
    {"doc_id": "audit_SUP-T1-0022.pdf::chunk::1", "kind": "chunk",
     "text": "Fire extinguisher inspection tags expired 4 months prior.",
     "source_file": "audit_SUP-T1-0022.pdf", "score": 0.81},
]


def test_baseline_returns_answer_with_canned_corpus_and_stub_llm():
    result = answer_with_vector_rag(
        "What does the audit say about SUP-T1-0022's subcontractors?",
        embedder=_FakeEmbedder(), index=_FakeIndex(_CANNED_CORPUS),
        chat_client=_StubChat("The audit flags a missing tier-2 fabric mill."),
    )
    assert result.answer == "The audit flags a missing tier-2 fabric mill."
    assert result.retrieved_doc_ids == [
        "audit_SUP-T1-0022.pdf::chunk::0", "audit_SUP-T1-0022.pdf::chunk::1",
    ]
    assert result.retrieved_source_files == [
        "audit_SUP-T1-0022.pdf", "audit_SUP-T1-0022.pdf",
    ]
    assert result.error is None
    assert result.latency_ms >= 0.0
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0


def test_baseline_no_hits_returns_no_evidence_without_calling_llm():
    calls = []

    class _CountingChat(_StubChat):
        def chat_text(self, *, system, user):
            calls.append(1)
            return super().chat_text(system=system, user=user)

    result = answer_with_vector_rag(
        "irrelevant question", embedder=_FakeEmbedder(), index=_FakeIndex([]),
        chat_client=_CountingChat("should not be called"),
    )
    assert result.answer == "No evidence found."
    assert result.retrieved_doc_ids == []
    assert calls == []   # LLM never invoked when there's nothing to answer from


def test_baseline_without_chat_client_skips_generation():
    result = answer_with_vector_rag(
        "q", embedder=_FakeEmbedder(), index=_FakeIndex(_CANNED_CORPUS),
        chat_client=None,
    )
    assert "retrieval only" in result.answer
    assert result.retrieved_doc_ids


def test_baseline_retrieval_failure_is_reported_not_raised():
    class _BrokenIndex:
        def search(self, *a, **kw):
            raise ConnectionError("no qdrant")

    result = answer_with_vector_rag(
        "q", embedder=_FakeEmbedder(), index=_BrokenIndex(), chat_client=None,
    )
    assert result.error is not None
    assert "retrieval unavailable" in result.error


def test_baseline_llm_failure_is_reported_not_raised():
    result = answer_with_vector_rag(
        "q", embedder=_FakeEmbedder(), index=_FakeIndex(_CANNED_CORPUS),
        chat_client=_StubChat("", raises=RuntimeError("session cap")),
    )
    assert result.error is not None
    assert "answer generation unavailable" in result.error
    # Retrieval already happened and should still be reported.
    assert result.retrieved_doc_ids
