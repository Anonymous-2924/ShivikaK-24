"""Covers the Phase 5 fix to build_from_extractions: name_to_id used to be
passed in as a hardcoded {} (see git history on cli/__main__.py), so no
llm_extracted edge could ever resolve. load_name_to_id_map replaces that
with a real map built from the structured ERP exports.
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

from src.graph.builder import load_name_to_id_map


def test_maps_supplier_name_to_id(tmp_path: Path) -> None:
    (tmp_path / "suppliers_export.json").write_text(json.dumps({
        "suppliers": [{"id": "SUP-0001", "name": "Horizon Textiles"}],
    }))
    mapping = load_name_to_id_map(tmp_path)
    assert mapping["Horizon Textiles"] == "SUP-0001"


def test_maps_sku_style_number_and_sku_id(tmp_path: Path) -> None:
    (tmp_path / "skus_export.json").write_text(json.dumps({
        "skus": [{"sku_id": "SKU-100", "style_number": "ST-42"}],
    }))
    mapping = load_name_to_id_map(tmp_path)
    assert mapping["ST-42"] == "SKU-100"
    assert mapping["SKU-100"] == "SKU-100"


def test_maps_plant_name_from_xml(tmp_path: Path) -> None:
    root = Element("PlantsExport")
    node = SubElement(root, "Plant", attrib={"id": "PLT-0007"})
    SubElement(node, "Name").text = "Dhaka Garment Factory 7"
    ElementTree(root).write(tmp_path / "plants_export.xml")
    mapping = load_name_to_id_map(tmp_path)
    assert mapping["Dhaka Garment Factory 7"] == "PLT-0007"


def test_maps_component_description_and_id(tmp_path: Path) -> None:
    (tmp_path / "components_export.json").write_text(json.dumps({
        "components": [{"id": "CMP-0003", "description": "Cotton twill 12oz"}],
    }))
    mapping = load_name_to_id_map(tmp_path)
    assert mapping["Cotton twill 12oz"] == "CMP-0003"
    assert mapping["CMP-0003"] == "CMP-0003"


def test_maps_route_id_identity(tmp_path: Path) -> None:
    (tmp_path / "routes_export.json").write_text(json.dumps({
        "routes": [{"route_id": "RT-0099"}],
    }))
    mapping = load_name_to_id_map(tmp_path)
    assert mapping["RT-0099"] == "RT-0099"


def test_missing_export_files_give_empty_map(tmp_path: Path) -> None:
    assert load_name_to_id_map(tmp_path) == {}


def test_build_from_extractions_resolves_names_via_the_map(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: an extraction record naming entities by their human
    name resolves onto the structured id, instead of being counted as
    unresolved (the bug this fix addresses)."""
    from src.graph.builder import build_from_extractions

    extractions = tmp_path / "extractions.jsonl"
    extractions.write_text(json.dumps({
        "source_file": "a.md",
        "entities": [
            {"name": "Horizon Textiles", "type": "Supplier"},
            {"name": "Nile Spinning Mills", "type": "Supplier"},
        ],
        "relations": [
            {"source": "Horizon Textiles", "target": "Nile Spinning Mills",
             "type": "supplied_by", "confidence": 0.8,
             "evidence_text": "ev"},
        ],
    }) + "\n")

    written_edges = []

    class _FakeWriter:
        def upsert_nodes(self, nodes):
            return len(list(nodes))

        def upsert_edges(self, edges):
            edges = list(edges)
            written_edges.extend(edges)
            return len(edges), 0

    class _FakeResolver:
        def resolve(self, entity_id):
            return entity_id

    name_to_id = {"Horizon Textiles": "SUP-0001", "Nile Spinning Mills": "SUP-0002"}
    stats = build_from_extractions(
        writer=_FakeWriter(), resolver=_FakeResolver(),
        extractions_path=extractions, name_to_id=name_to_id,
        log_fn=lambda m: None,
    )
    assert stats.edges_skipped_unresolved == 0
    assert stats.edges_written == 1
    assert written_edges[0].source_id == "SUP-0001"
    assert written_edges[0].target_id == "SUP-0002"
