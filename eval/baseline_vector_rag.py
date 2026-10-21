"""Plain vector-RAG baseline — what Phase 6 benchmarks GraphRAG against.

Deliberately dumb, per the brief: embed the question, top-k Qdrant,
concatenate the chunk texts, one LLM call for the answer. No graph, no
DuckDB, no router, no recombiner. This is the ceiling on how good
"just embed everything and ask an LLM" gets on this corpus.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BaselineResult:
    question: str
    answer: str
    retrieved_doc_ids: list[str] = field(default_factory=list)
    retrieved_source_files: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None
    error: str | None = None


SYSTEM_PROMPT = (
    "Answer the question using ONLY the context chunks below. If the "
    "context doesn't contain the answer, say so plainly rather than "
    "guessing. Keep the answer to 2-4 sentences."
)


def answer_with_vector_rag(question: str, *, embedder, index, chat_client=None,
                            top_k: int = 20) -> BaselineResult:
    """``embedder``/``index`` are the same Phase 3 Embedder/QdrantIndex
    (or test doubles with that shape). ``chat_client`` needs
    ``chat_text(system=..., user=...) -> object with .text`` (the same
    shape as ``src.extract.client.OllamaChat.chat_text``) — pass None to
    skip answer generation and just measure retrieval (useful when no
    LLM is reachable; the result's ``answer`` then explains why)."""
    t0 = time.monotonic()
    try:
        vector = embedder.embed_one(question)
        hits = index.search(vector, top_k=top_k, kind="chunk")
    except Exception as exc:   # noqa: BLE001
        return BaselineResult(
            question=question, answer="",
            latency_ms=(time.monotonic() - t0) * 1000,
            error=f"retrieval unavailable: {type(exc).__name__}: {exc}",
        )

    doc_ids = [h.get("doc_id", "") for h in hits]
    source_files = [h.get("source_file", "") for h in hits]
    context = "\n\n---\n\n".join(h.get("text", "") for h in hits)

    if not hits:
        latency_ms = (time.monotonic() - t0) * 1000
        return BaselineResult(
            question=question, answer="No evidence found.",
            retrieved_doc_ids=doc_ids, retrieved_source_files=source_files,
            latency_ms=latency_ms,
        )

    if chat_client is None:
        latency_ms = (time.monotonic() - t0) * 1000
        return BaselineResult(
            question=question,
            answer="(retrieval only — no chat_client supplied, answer "
                    "generation skipped)",
            retrieved_doc_ids=doc_ids, retrieved_source_files=source_files,
            latency_ms=latency_ms,
        )

    try:
        res = chat_client.chat_text(
            system=SYSTEM_PROMPT,
            user=f"QUESTION: {question}\n\nCONTEXT:\n{context}",
        )
        answer = res.text
    except Exception as exc:   # noqa: BLE001
        latency_ms = (time.monotonic() - t0) * 1000
        return BaselineResult(
            question=question, answer="",
            retrieved_doc_ids=doc_ids, retrieved_source_files=source_files,
            latency_ms=latency_ms,
            error=f"answer generation unavailable: {type(exc).__name__}: {exc}",
        )

    latency_ms = (time.monotonic() - t0) * 1000
    from eval.metrics import estimate_tokens
    return BaselineResult(
        question=question, answer=answer,
        retrieved_doc_ids=doc_ids, retrieved_source_files=source_files,
        latency_ms=latency_ms,
        prompt_tokens=estimate_tokens(SYSTEM_PROMPT + context + question),
        completion_tokens=estimate_tokens(answer),
        model=getattr(chat_client, "model", None),
    )
