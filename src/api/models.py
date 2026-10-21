"""Pydantic request/response models for the Phase 7 API.

Deliberately thin, per the brief: query, ingest status, graph stats,
entity lookup. No auth, no multi-tenant — see README scope boundaries.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class QueryRequest(BaseModel):
    question: str
    as_of: str | None = Field(
        default=None, description="ISO date (YYYY-MM-DD), optional.")


class SourceRefOut(BaseModel):
    doc_id: str
    kind: str
    detail: dict = Field(default_factory=dict)


class SemanticHitOut(BaseModel):
    doc_id: str
    kind: str
    text: str
    source_file: str
    score: float
    confidence: float
    extraction_method: str


class PathRecordOut(BaseModel):
    target_id: str
    target_type: str
    hops: int
    path_nodes: list[dict] = Field(default_factory=list)
    path_rels: list[dict] = Field(default_factory=list)


class QuantResultOut(BaseModel):
    metric: str
    parquet_path: str
    column_used: str | None
    result: dict | None
    note: str


class QueryResponse(BaseModel):
    question: str
    categories: list[str]
    direct_answer: str
    confidence: float
    as_of: str | None
    source_refs: list[SourceRefOut]
    supporting_chunks: list[SemanticHitOut]
    graph_paths: list[PathRecordOut]
    quantitative: list[QuantResultOut]


class IngestStatusResponse(BaseModel):
    by_track_and_outcome: dict[str, int] = Field(default_factory=dict)
    total_rows: int
    last_run_at: str | None
    audit_db_found: bool


class GraphStatsResponse(BaseModel):
    node_counts: dict[str, int] = Field(default_factory=dict)
    edge_counts: dict[str, int] = Field(default_factory=dict)
    reachable: bool


class EntityResponse(BaseModel):
    id: str
    labels: list[str]
    properties: dict
