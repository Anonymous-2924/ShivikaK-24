"""Phase 1 sanity: every config file parses and holds the shape the rest
of the project will rely on. Catches a typo in settings.yaml the moment
it lands, long before Phase 3 tries to use it.
"""
from __future__ import annotations

import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).parent.parent
CONFIG = ROOT / "config"

ALLOWED_NODE_TYPES = {
    "SKU", "Component", "Supplier", "Plant", "Site", "Geography",
    "Route", "Port", "Event", "Document", "DataTable",
}
ALLOWED_RELATIONS = {
    "contains", "supplied_by", "manufactured_at", "located_in", "ships_via",
    "disrupted_by", "substitutes_for", "evidenced_by", "has_financials",
}
REQUIRED_EDGE_FIELDS = {
    "confidence", "valid_from", "valid_to", "source_ref", "extraction_method",
}


def test_settings_yaml_parses_and_has_required_sections() -> None:
    s = yaml.safe_load((CONFIG / "settings.yaml").read_text())
    for section in ("paths", "ingest", "extraction", "verifier",
                    "resolver", "graph", "retrieval", "eval"):
        assert section in s, f"settings.yaml missing section: {section}"
    assert set(s["extraction"]["allowed_node_types"]) == ALLOWED_NODE_TYPES
    assert set(s["extraction"]["allowed_relations"]) == ALLOWED_RELATIONS
    assert set(s["graph"]["required_edge_fields"]) == REQUIRED_EDGE_FIELDS


def test_aliases_yaml_parses() -> None:
    text = (CONFIG / "aliases.yaml").read_text()
    # Empty-but-valid YAML (all comments) parses to None; that's fine.
    data = yaml.safe_load(text)
    assert data is None or isinstance(data, dict)


def test_extraction_schema_is_valid_json_and_matches_vocab() -> None:
    schema = json.loads((CONFIG / "extraction_schema.json").read_text())
    entity_type_enum = schema["properties"]["entities"]["items"]["properties"]["type"]["enum"]
    rel_type_enum = schema["properties"]["relations"]["items"]["properties"]["type"]["enum"]
    assert set(entity_type_enum) == ALLOWED_NODE_TYPES
    assert set(rel_type_enum) == ALLOWED_RELATIONS
