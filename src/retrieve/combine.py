"""Recombiner: dispatcher outputs -> one answer object.

Confidence is the bottleneck across whatever was actually used to answer
the question (brief rule: ``min()`` across the weakest link, not an
average — one shaky edge in an otherwise-confident path should pull the
whole answer down, not get diluted by eight confident ones).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.retrieve.quantitative import QuantResult
from src.retrieve.semantic import SemanticHit
from src.retrieve.structural import PathRecord


@dataclass
class SourceRef:
    doc_id: str
    kind: str          # "narrative" | "graph_edge" | "data_table"
    detail: dict = field(default_factory=dict)


@dataclass
class AnswerObject:
    question: str
    categories: list[str]
    direct_answer: str
    supporting_chunks: list[SemanticHit]
    graph_paths: list[PathRecord]
    quantitative: list[QuantResult]
    confidence: float
    source_refs: list[SourceRef]
    as_of: str | None = None


def combine(*, question: str, categories: set[str],
            semantic_hits: list[SemanticHit] | None = None,
            paths: list[PathRecord] | None = None,
            quant_results: list[QuantResult] | None = None,
            as_of: str | None = None) -> AnswerObject:
    semantic_hits = semantic_hits or []
    paths = paths or []
    quant_results = quant_results or []

    confidences: list[float] = []
    source_refs: list[SourceRef] = []

    for h in semantic_hits:
        confidences.append(h.confidence)
        source_refs.append(SourceRef(
            doc_id=h.doc_id, kind="narrative",
            detail={"source_file": h.source_file, "score": h.score,
                    "extraction_method": h.extraction_method},
        ))

    for p in paths:
        for rel in p.path_rels:
            conf = rel.get("confidence")
            if isinstance(conf, (int, float)):
                confidences.append(float(conf))
            sr = rel.get("source_ref") or {}
            doc_id = sr.get("doc_id") if isinstance(sr, dict) else None
            source_refs.append(SourceRef(
                doc_id=doc_id or "unknown", kind="graph_edge",
                detail={"rel_type": rel.get("type"),
                        "extraction_method": rel.get("extraction_method"),
                        "target": p.target_id},
            ))

    for q in quant_results:
        if q.result is not None:
            # A matched aggregate is as trustworthy as the DataTable it
            # read from (data cards enter the graph at manual/structured
            # confidence — we don't have that confidence threaded through
            # here yet, so treat a successful match as fully confident and
            # let the real bottleneck come from the graph path that led
            # to it).
            source_refs.append(SourceRef(
                doc_id=q.parquet_path, kind="data_table",
                detail={"metric": q.metric, "column": q.column_used,
                        "result": q.result},
            ))

    confidence = min(confidences) if confidences else 0.0
    direct_answer = _render_direct_answer(
        semantic_hits=semantic_hits, paths=paths, quant_results=quant_results,
    )

    return AnswerObject(
        question=question, categories=sorted(categories),
        direct_answer=direct_answer,
        supporting_chunks=semantic_hits, graph_paths=paths,
        quantitative=quant_results, confidence=round(confidence, 4),
        source_refs=source_refs, as_of=as_of,
    )


def _render_direct_answer(*, semantic_hits: list[SemanticHit],
                           paths: list[PathRecord],
                           quant_results: list[QuantResult]) -> str:
    parts: list[str] = []
    if paths:
        targets = sorted({p.target_id for p in paths})
        parts.append(
            f"{len(targets)} {paths[0].target_type}(s) reachable: "
            f"{', '.join(targets[:10])}" + (" ..." if len(targets) > 10 else "")
        )
    for q in quant_results:
        if q.result is not None:
            parts.append(f"{q.metric}: {q.result}")
        else:
            parts.append(f"{q.metric}: {q.note}")
    if not parts and semantic_hits:
        top = semantic_hits[0]
        parts.append(f"Best narrative match ({top.source_file}): "
                      f"{top.text[:240]}")
    return " | ".join(parts) if parts else "No evidence found."
