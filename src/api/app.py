"""Phase 7 API — thin on purpose.

Four endpoints, per the brief: query, ingest status, graph stats, entity
lookup. No auth, no multi-tenant (see README scope boundaries) — this is
a research/analysis tool, not a production service.

Every endpoint degrades gracefully when a backend (Neo4j, Qdrant,
Ollama) is unreachable, same philosophy as the ingest pipeline and the
retrieval service: report what's actually true ("Neo4j unreachable"),
never silently return an empty-but-misleading 200.
"""
from __future__ import annotations

import asyncio
import dataclasses
import sqlite3
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from src.api.models import (
    EntityResponse,
    GraphStatsResponse,
    HealthResponse,
    IngestStatusResponse,
    PathRecordOut,
    QuantResultOut,
    QueryRequest,
    QueryResponse,
    SemanticHitOut,
    SourceRefOut,
)


@dataclasses.dataclass
class ApiConfig:
    port: int = 8000
    cors_origins: list[str] = dataclasses.field(default_factory=list)
    max_query_timeout_s: float = 30.0
    audit_db_path: Path = Path("data/processed/audit.sqlite")

    @classmethod
    def load(cls, settings_path: Path = Path("config/settings.yaml")) -> ApiConfig:
        s = yaml.safe_load(settings_path.read_text())
        a = s.get("api", {}) or {}
        return cls(
            port=int(a.get("port", 8000)),
            cors_origins=list(a.get("cors_origins", [])),
            max_query_timeout_s=float(a.get("max_query_timeout_s", 30.0)),
        )


def create_app(cfg: ApiConfig | None = None) -> FastAPI:
    cfg = cfg or ApiConfig.load()
    app = FastAPI(title="Blast Radius Engine API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins or ["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.state.cfg = cfg

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/query", response_model=QueryResponse)
    async def query(req: QueryRequest) -> QueryResponse:
        from src.retrieve.service import answer_question

        try:
            result = await asyncio.wait_for(
                run_in_threadpool(
                    answer_question, req.question, as_of=req.as_of,
                    log_fn=lambda m: None,
                ),
                timeout=app.state.cfg.max_query_timeout_s,
            )
        except TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail=f"query exceeded {app.state.cfg.max_query_timeout_s}s timeout",
            ) from exc

        return QueryResponse(
            question=result.question,
            categories=result.categories,
            direct_answer=result.direct_answer,
            confidence=result.confidence,
            as_of=result.as_of,
            source_refs=[SourceRefOut(doc_id=sr.doc_id, kind=sr.kind,
                                        detail=sr.detail)
                         for sr in result.source_refs],
            supporting_chunks=[SemanticHitOut(**dataclasses.asdict(h))
                               for h in result.supporting_chunks],
            graph_paths=[PathRecordOut(**dataclasses.asdict(p))
                        for p in result.graph_paths],
            quantitative=[QuantResultOut(**dataclasses.asdict(q))
                         for q in result.quantitative],
        )

    @app.get("/ingest/status", response_model=IngestStatusResponse)
    def ingest_status() -> IngestStatusResponse:
        db_path = app.state.cfg.audit_db_path
        if not db_path.exists():
            return IngestStatusResponse(
                by_track_and_outcome={}, total_rows=0, last_run_at=None,
                audit_db_found=False,
            )
        conn = sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT track, ok, COUNT(*) AS n FROM extractions "
                "GROUP BY track, ok"
            ).fetchall()
            by_track = {
                f"{r['track']}:{'ok' if r['ok'] else 'fail'}": r["n"]
                for r in rows
            }
            total = conn.execute("SELECT COUNT(*) FROM extractions").fetchone()[0]
            last_run = conn.execute(
                "SELECT MAX(ended_at) FROM extractions"
            ).fetchone()[0]
        finally:
            conn.close()
        return IngestStatusResponse(
            by_track_and_outcome=by_track, total_rows=total,
            last_run_at=last_run, audit_db_found=True,
        )

    @app.get("/graph/stats", response_model=GraphStatsResponse)
    def graph_stats() -> GraphStatsResponse:
        driver = _neo4j_driver()
        if driver is None:
            return GraphStatsResponse(node_counts={}, edge_counts={},
                                       reachable=False)
        try:
            with driver.session() as session:
                node_rows = session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n"
                )
                node_counts = {r["label"]: r["n"] for r in node_rows}
                edge_rows = session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n"
                )
                edge_counts = {r["t"]: r["n"] for r in edge_rows}
        finally:
            driver.close()
        return GraphStatsResponse(node_counts=node_counts,
                                   edge_counts=edge_counts, reachable=True)

    @app.get("/entity/{entity_id}", response_model=EntityResponse)
    def entity(entity_id: str) -> EntityResponse:
        driver = _neo4j_driver()
        if driver is None:
            raise HTTPException(status_code=503, detail="Neo4j unreachable")
        try:
            with driver.session() as session:
                row = session.run(
                    "MATCH (n {id: $id}) "
                    "RETURN n.id AS id, labels(n) AS labels, properties(n) AS props",
                    id=entity_id,
                ).single()
        finally:
            driver.close()
        if row is None:
            raise HTTPException(status_code=404,
                                 detail=f"no entity with id {entity_id!r}")
        return EntityResponse(id=row["id"], labels=row["labels"],
                              properties=dict(row["props"]))

    return app


def _neo4j_driver():
    import os
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.environ.get("NEO4J_USER", "neo4j"),
                  os.environ.get("NEO4J_PASSWORD", "")),
        )
        with driver.session() as s:
            s.run("RETURN 1")
        return driver
    except Exception:   # noqa: BLE001
        return None


app = create_app()
