"""Recombiner shape: confidence bottleneck, source_refs, direct_answer."""
from __future__ import annotations

from src.retrieve.combine import combine
from src.retrieve.quantitative import QuantResult
from src.retrieve.semantic import SemanticHit
from src.retrieve.structural import PathRecord


def test_combine_empty_dispatchers_gives_zero_confidence_and_no_sources():
    answer = combine(question="q", categories={"semantic"})
    assert answer.confidence == 0.0
    assert answer.source_refs == []
    assert answer.direct_answer == "No evidence found."


def test_confidence_is_the_minimum_across_sources():
    hits = [
        SemanticHit(doc_id="a", kind="chunk", text="t", source_file="a.md",
                    score=0.9, confidence=0.95, extraction_method="structured"),
    ]
    paths = [
        PathRecord(target_id="SKU-1", target_type="SKU", hops=2,
                   path_nodes=[], path_rels=[
                       {"type": "supplied_by", "confidence": 0.4,
                        "extraction_method": "llm_extracted",
                        "source_ref": {"doc_id": "x.md"}},
                   ]),
    ]
    answer = combine(question="q", categories={"semantic", "structural"},
                      semantic_hits=hits, paths=paths)
    # The weakest link (0.4 on the graph edge) sets the bottleneck, not
    # the average of 0.95 and 0.4.
    assert answer.confidence == 0.4


def test_source_refs_cover_all_three_dispatchers():
    hits = [SemanticHit(doc_id="a", kind="chunk", text="t", source_file="a.md",
                         score=0.9, confidence=0.9, extraction_method="structured")]
    paths = [PathRecord(target_id="SKU-1", target_type="SKU", hops=1,
                         path_nodes=[], path_rels=[
                             {"type": "supplied_by", "confidence": 0.8,
                              "extraction_method": "structured",
                              "source_ref": {"doc_id": "y.json"}},
                         ])]
    quant = [QuantResult(metric="revenue", parquet_path="/d/x.parquet",
                          column_used="revenue_usd",
                          result={"total": 500.0}, note="matched")]
    answer = combine(question="q", categories={"semantic", "structural", "quantitative"},
                      semantic_hits=hits, paths=paths, quant_results=quant)
    kinds = {sr.kind for sr in answer.source_refs}
    assert kinds == {"narrative", "graph_edge", "data_table"}


def test_direct_answer_summarises_paths_and_quant():
    paths = [
        PathRecord(target_id="SKU-1", target_type="SKU", hops=1, path_nodes=[], path_rels=[]),
        PathRecord(target_id="SKU-2", target_type="SKU", hops=2, path_nodes=[], path_rels=[]),
    ]
    quant = [QuantResult(metric="revenue", parquet_path="/d/x.parquet",
                          column_used="revenue_usd", result={"total": 300.0},
                          note="matched")]
    answer = combine(question="q", categories={"structural", "quantitative"},
                      paths=paths, quant_results=quant)
    assert "SKU-1" in answer.direct_answer
    assert "SKU-2" in answer.direct_answer
    assert "revenue" in answer.direct_answer


def test_as_of_is_threaded_through():
    answer = combine(question="q", categories={"semantic"}, as_of="2026-02-01")
    assert answer.as_of == "2026-02-01"
