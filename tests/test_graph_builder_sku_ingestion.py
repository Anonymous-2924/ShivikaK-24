"""Phase 6 addition: build_from_structured never read skus_export.json,
so no SKU node ever existed in the graph — discovered while building the
eval harness against a real Neo4j instance (every exposure-tracing
question returned zero results for a trivial reason, not a retrieval
limitation). Covers the fix: SKU nodes + contains/manufactured_at/
supplied_by edges built from the SKU export, same shape as the other
structured sources.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.graph.builder import build_from_structured


class _FakeWriter:
    def __init__(self) -> None:
        self.nodes: list = []
        self.edges: list = []

    def upsert_nodes(self, nodes):
        nodes = list(nodes)
        self.nodes.extend(nodes)
        return len(nodes)

    def upsert_edges(self, edges):
        edges = list(edges)
        self.edges.extend(edges)
        return len(edges), 0


class _FakeResolver:
    def resolve(self, entity_id):
        return entity_id


def test_build_from_structured_ingests_skus(tmp_path: Path) -> None:
    (tmp_path / "skus_export.json").write_text(json.dumps({
        "skus": [{
            "sku_id": "SKU-100", "style_number": "ST-42",
            "garment_type": "jacket", "fit": "regular", "color": "navy",
            "size": "M", "season": "FW26", "retail_price_usd": 89.0,
            "cost_target_usd": 22.0,
            "tier1_supplier": "SUP-T1-0001", "plant": "PLT-0001",
            "bom": [{"component_id": "CMP-0001", "qty": 2},
                    {"component_id": "CMP-0002", "qty": 1}],
        }],
    }))
    writer = _FakeWriter()
    stats = build_from_structured(
        writer=writer, resolver=_FakeResolver(),
        structured_json_dir=tmp_path, log_fn=lambda m: None,
    )
    sku_nodes = [n for n in writer.nodes if n.type == "SKU"]
    assert len(sku_nodes) == 1
    assert sku_nodes[0].id == "SKU-100"
    assert sku_nodes[0].props["style_number"] == "ST-42"

    rel_types = {(e.source_type, e.rel_type, e.target_type) for e in writer.edges}
    assert ("SKU", "supplied_by", "Supplier") in rel_types
    assert ("SKU", "manufactured_at", "Plant") in rel_types
    assert ("SKU", "contains", "Component") in rel_types

    contains_edges = [e for e in writer.edges if e.rel_type == "contains"]
    assert {e.target_id for e in contains_edges} == {"CMP-0001", "CMP-0002"}
    assert stats.sources_processed == 1


def test_build_from_structured_skips_sku_edges_with_missing_refs(tmp_path: Path) -> None:
    (tmp_path / "skus_export.json").write_text(json.dumps({
        "skus": [{
            "sku_id": "SKU-200", "tier1_supplier": None, "plant": "",
            "bom": [],
        }],
    }))
    writer = _FakeWriter()
    build_from_structured(
        writer=writer, resolver=_FakeResolver(),
        structured_json_dir=tmp_path, log_fn=lambda m: None,
    )
    sku_edges = [e for e in writer.edges if e.source_type == "SKU"]
    assert sku_edges == []


def test_build_from_structured_missing_sku_export_is_a_noop(tmp_path: Path) -> None:
    writer = _FakeWriter()
    stats = build_from_structured(
        writer=writer, resolver=_FakeResolver(),
        structured_json_dir=tmp_path, log_fn=lambda m: None,
    )
    assert [n for n in writer.nodes if n.type == "SKU"] == []
    assert stats.sources_processed == 0
