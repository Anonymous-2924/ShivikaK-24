"""Pluggable embedding providers.

Three providers, chosen by config:

* ``local``   – sentence-transformers (e.g. all-MiniLM-L6-v2), CPU-friendly,
  downloaded once (~80 MB). Preferred when available.
* ``ollama``  – cloud embeddings via the Ollama API (if the account/model
  supports it).
* ``hashing`` – a deterministic, dependency-free hashing embedder. Not
  semantically strong, but lets the full pipeline run and be tested with no
  model download. Clearly labelled as a fallback.

Embeddings are generated in bounded batches to respect the memory budget.
"""
from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Sequence

from src.utils.logging import get_logger

log = get_logger(__name__)


class EmbeddingProvider(ABC):
    name: str
    dim: int

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def embed_batched(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            out.extend(self.embed(texts[i : i + batch_size]))
        return out


class HashingEmbedder(EmbeddingProvider):
    """Deterministic bag-of-words hashing embedder (fallback, no deps)."""

    name = "hashing"

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in text.lower().split():
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 1) & 1 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class LocalEmbedder(EmbeddingProvider):
    """sentence-transformers embedder (optional heavy dep)."""

    name = "local"

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # raises if missing

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vecs = self._model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return [v.tolist() for v in vecs]


class OllamaEmbedder(EmbeddingProvider):
    """Cloud embeddings via the Ollama embeddings endpoint."""

    name = "ollama"

    def __init__(self, client, model: str, dim: int = 768):
        self._client = client
        self._model = model
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._client.embed(self._model, t) for t in texts]


def build_embedder(settings) -> EmbeddingProvider:
    """Construct the configured embedder, falling back gracefully with a log."""
    provider = settings.embedding_provider
    if provider == "local":
        try:
            emb = LocalEmbedder(settings.embedding_model)
            log.info("Using local sentence-transformers embedder (dim=%d).", emb.dim)
            return emb
        except Exception as exc:
            log.warning("Local embedder unavailable (%s); falling back to hashing embedder.", exc)
            return HashingEmbedder(settings.embedding_dim)
    if provider == "ollama":
        try:
            from src.llm.ollama_client import OllamaClient

            client = OllamaClient.from_settings(settings)
            return OllamaEmbedder(client, settings.embedding_model, settings.embedding_dim)
        except Exception as exc:
            log.warning("Ollama embedder unavailable (%s); falling back to hashing embedder.", exc)
            return HashingEmbedder(settings.embedding_dim)
    return HashingEmbedder(settings.embedding_dim)
