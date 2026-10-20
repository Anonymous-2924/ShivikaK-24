"""Local Ollama embedding client.

Thin wrapper around ``ollama.Client`` that pins the model and verifies
the dimension matches the configured ``OLLAMA_EMBED_DIM``. The dimension
check is non-cosmetic: Qdrant collections are created with a fixed
vector size, and a mismatch at upsert time is a hard failure that
produces incomprehensible errors — far better to fail fast on startup.
"""
from __future__ import annotations

from collections.abc import Sequence


class Embedder:
    def __init__(self, *, host: str, model: str,
                 expected_dim: int | None = None) -> None:
        import ollama  # local import keeps this file importable in test envs
        self.model = model
        self.client = ollama.Client(host=host)
        self.expected_dim = expected_dim
        self._dim: int | None = None

    def ping(self) -> int:
        """Embed one dummy string, verify dimension, cache it. Returns dim."""
        vec = self.embed_one("ping")
        if self.expected_dim is not None and len(vec) != self.expected_dim:
            raise RuntimeError(
                f"embedding dim mismatch for model {self.model!r}: "
                f"config says {self.expected_dim}, model returned {len(vec)}. "
                f"Fix OLLAMA_EMBED_DIM in .env before building the Qdrant "
                f"collection — the dim is baked into the collection."
            )
        self._dim = len(vec)
        return self._dim

    def dim(self) -> int:
        if self._dim is None:
            return self.ping()
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        res = self.client.embeddings(model=self.model, prompt=text)
        return list(res["embedding"])

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        # Ollama's /api/embeddings is one-at-a-time; batching would need
        # /api/embed on newer servers. Phase 3 corpus is modest; sequential
        # is fine. Revisit when ingest latency actually hurts.
        return [self.embed_one(t) for t in texts]
