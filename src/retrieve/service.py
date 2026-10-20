"""Top-level entry point: question in, ``AnswerObject`` out.

Wires the router to the three dispatchers and the recombiner. This is
the module the CLI's ``query`` command (and, in Phase 7, the API) calls.
Connections (Qdrant/Ollama/Neo4j/DuckDB) are built lazily and are best-
effort: if a backend is unreachable, that category's dispatch is skipped
and noted, rather than failing the whole query — consistent with how
``src/ingest/pipeline.py`` treats an unreachable Qdrant.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.retrieve import quantitative, semantic, structural
from src.retrieve.combine import AnswerObject, combine
from src.retrieve.router import QUANTITATIVE, SEMANTIC, STRUCTURAL, classify_query


@dataclass
class QueryConfig:
    qdrant_url: str
    qdrant_api_key: str | None
    ollama_embed_host: str
    ollama_embed_model: str
    ollama_embed_dim: int
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    top_k_semantic: int
    hops_structural: int

    @classmethod
    def load(cls, settings_path: Path = Path("config/settings.yaml")) -> QueryConfig:
        s = yaml.safe_load(settings_path.read_text())
        r = s.get("retrieval", {})
        return cls(
            qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.environ.get("QDRANT_API_KEY") or None,
            ollama_embed_host=os.environ.get("OLLAMA_EMBED_HOST",
                                              "http://localhost:11434"),
            ollama_embed_model=os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3"),
            ollama_embed_dim=int(os.environ.get("OLLAMA_EMBED_DIM", "1024")),
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD", ""),
            top_k_semantic=int(r.get("default_top_k_semantic", 20)),
            hops_structural=int(r.get("default_hops_structural", 3)),
        )


def answer_question(question: str, *, as_of: str | None = None,
                     cfg: QueryConfig | None = None,
                     log_fn=print) -> AnswerObject:
    cfg = cfg or QueryConfig.load()
    plan = classify_query(question, as_of=as_of)
    log_fn(f"[query] categories={sorted(plan.categories)} "
           f"entity_hints={plan.entity_hints} as_of={plan.as_of}")

    semantic_hits = []
    paths = []
    quant_results = []

    if SEMANTIC in plan.categories:
        try:
            embedder, index = _init_semantic(cfg)
            semantic_hits = semantic.semantic_search(
                question, embedder=embedder, index=index,
                top_k=cfg.top_k_semantic,
            )
        except Exception as exc:   # noqa: BLE001
            log_fn(f"[query] semantic dispatch unavailable: "
                   f"{type(exc).__name__}: {exc}")

    entity_id = None
    driver = None
    if STRUCTURAL in plan.categories or QUANTITATIVE in plan.categories:
        try:
            driver = _init_neo4j(cfg)
            entity_id = _resolve_entity(driver, plan.entity_hints)
        except Exception as exc:   # noqa: BLE001
            log_fn(f"[query] Neo4j unavailable: {type(exc).__name__}: {exc}")

    if STRUCTURAL in plan.categories and driver is not None:
        if entity_id is None:
            log_fn("[query] structural: no entity hint resolved to a graph node")
        else:
            paths = structural.exposure_paths(
                driver, entity_id, max_hops=cfg.hops_structural,
                as_of=plan.as_of,
            )

    if QUANTITATIVE in plan.categories and driver is not None and entity_id is not None:
        tables = quantitative.find_datatable_for_entity(driver, entity_id)
        if tables:
            try:
                import duckdb
                conn = duckdb.connect()
                for t in tables:
                    for metric in ("revenue", "buffer_days", "lead_time"):
                        quant_results.append(quantitative.run_metric(
                            conn, t["parquet_path"], metric))
            except Exception as exc:   # noqa: BLE001
                log_fn(f"[query] quantitative dispatch unavailable: "
                       f"{type(exc).__name__}: {exc}")

    if driver is not None:
        driver.close()

    return combine(
        question=question, categories=plan.categories,
        semantic_hits=semantic_hits, paths=paths,
        quant_results=quant_results, as_of=plan.as_of,
    )


def _resolve_entity(driver, hints: list[str]) -> str | None:
    for hint in hints:
        eid = structural.find_entity_id(driver, hint)
        if eid:
            return eid
    return None


def _init_semantic(cfg: QueryConfig):
    from src.index.embeddings import Embedder
    from src.index.qdrant import QdrantIndex
    emb = Embedder(host=cfg.ollama_embed_host, model=cfg.ollama_embed_model,
                    expected_dim=cfg.ollama_embed_dim)
    dim = emb.ping()
    idx = QdrantIndex(url=cfg.qdrant_url, vector_dim=dim,
                       api_key=cfg.qdrant_api_key)
    return emb, idx


def _init_neo4j(cfg: QueryConfig):
    from neo4j import GraphDatabase
    return GraphDatabase.driver(cfg.neo4j_uri,
                                 auth=(cfg.neo4j_user, cfg.neo4j_password))
