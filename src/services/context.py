"""Application composition root.

Builds and caches the shared services (settings, stores, index, query engine,
crew) from configuration. Degrades gracefully: if the LLM key is absent the app
still parses, indexes and retrieves (evidence-only answers).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from src.config.settings import Settings, get_settings
from src.rag.embeddings import EmbeddingProvider, build_embedder
from src.rag.indexing import RagIndex
from src.rag.query_engine import QueryEngine
from src.rag.reranking import RerankStatus, build_reranker
from src.storage.metadata_store import MetadataStore
from src.storage.qdrant_store import QdrantStore
from src.storage.repositories import ChunkRepository
from src.utils.logging import configure_logging, get_logger

log = get_logger(__name__)


@dataclass
class AppContext:
    settings: Settings
    metadata_store: MetadataStore
    chunk_repo: ChunkRepository
    index: RagIndex
    engine: QueryEngine
    embedder: EmbeddingProvider
    rerank_status: RerankStatus
    llm_available: bool


def build_context(settings: Optional[Settings] = None) -> AppContext:
    settings = settings or get_settings()
    configure_logging(settings.log_level, extra_secrets=[
        s for s in (settings.ollama_api_key, settings.qdrant_api_key) if s
    ])
    settings.ensure_dirs()

    embedder = build_embedder(settings)
    store = QdrantStore(
        mode=settings.qdrant_mode, path=settings.qdrant_path, url=settings.qdrant_url,
        api_key=settings.qdrant_api_key, collection=settings.qdrant_collection,
        dim=embedder.dim,
    )
    chunk_repo = ChunkRepository(str(settings.paths()["metadata"] / "chunks.db"))
    metadata_store = MetadataStore(settings.metadata_db_path)
    index = RagIndex(store, chunk_repo, embedder)

    llm_client = None
    model = None
    llm_available = False
    if settings.ollama_configured():
        try:
            from src.llm.ollama_client import OllamaClient

            llm_client = OllamaClient.from_settings(settings)
            model = settings.ollama_model
            llm_available = True
        except Exception as exc:
            log.warning("LLM client init failed: %s", exc)

    reranker, rerank_status = build_reranker(settings)
    engine = QueryEngine(index, llm_client=llm_client, model=model, reranker=reranker)

    return AppContext(
        settings=settings, metadata_store=metadata_store, chunk_repo=chunk_repo,
        index=index, engine=engine, embedder=embedder, rerank_status=rerank_status,
        llm_available=llm_available,
    )


@lru_cache(maxsize=1)
def get_context() -> AppContext:
    return build_context()


def reset_context() -> None:
    get_context.cache_clear()
