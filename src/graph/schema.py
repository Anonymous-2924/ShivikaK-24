"""Deterministic triple validator.

The brief: 'Enforce schema validity deterministically: reject triples
that violate type rules (e.g. a Geography cannot be supplied_by a SKU)
before they reach the graph. This is free and catches a lot of model
noise.'

A triple is a (source_type, relation_type, target_type) tuple. The set
below is the authoritative whitelist. Everything else is rejected.
"""
from __future__ import annotations

from src.extract.prompts import ALLOWED_NODE_TYPES, ALLOWED_RELATION_TYPES

# Each entry: (source_type, relation, target_type).
# Keep this list conservative — it is easier to add later than to
# unpollute the graph of edges we should not have allowed.
VALID_TRIPLES: frozenset[tuple[str, str, str]] = frozenset({
    # Composition
    ("SKU", "contains", "Component"),
    ("Component", "contains", "Component"),
    # Sourcing
    ("Component", "supplied_by", "Supplier"),
    ("Supplier",  "supplied_by", "Supplier"),   # tier chain
    ("SKU",       "supplied_by", "Supplier"),
    ("Plant",     "supplied_by", "Supplier"),   # plant belongs to its parent supplier
    # Manufacturing
    ("SKU",       "manufactured_at", "Plant"),
    ("Component", "manufactured_at", "Plant"),
    # Geography
    ("Supplier",  "located_in", "Geography"),
    ("Plant",     "located_in", "Geography"),
    ("Site",      "located_in", "Geography"),
    ("Port",      "located_in", "Geography"),
    # Logistics
    ("SKU",       "ships_via", "Route"),
    ("Component", "ships_via", "Route"),
    ("Route",     "ships_via", "Port"),
    # Disruption
    ("Supplier",  "disrupted_by", "Event"),
    ("Plant",     "disrupted_by", "Event"),
    ("Port",      "disrupted_by", "Event"),
    ("Route",     "disrupted_by", "Event"),
    ("Geography", "disrupted_by", "Event"),
    # Substitution
    ("Component", "substitutes_for", "Component"),
    ("Supplier",  "substitutes_for", "Supplier"),
    # Evidence (edges point from the asserted fact to its source Document)
    # Allow any entity type to be evidenced by a Document.
    *((etype, "evidenced_by", "Document") for etype in ALLOWED_NODE_TYPES),
    # Financial / data-table links
    ("Supplier",  "has_financials", "DataTable"),
    ("Plant",     "has_financials", "DataTable"),
})


REQUIRED_EDGE_FIELDS = {"confidence", "valid_from", "valid_to",
                        "source_ref", "extraction_method"}
ALLOWED_EXTRACTION_METHODS = {"structured", "llm_extracted",
                              "inferred", "manual", "vision"}


class SchemaViolation(ValueError):
    pass


def is_valid_triple(src_type: str, rel: str, tgt_type: str) -> bool:
    if src_type not in ALLOWED_NODE_TYPES:
        return False
    if tgt_type not in ALLOWED_NODE_TYPES:
        return False
    if rel not in ALLOWED_RELATION_TYPES:
        return False
    return (src_type, rel, tgt_type) in VALID_TRIPLES


def validate_edge(src_type: str, rel: str, tgt_type: str,
                   edge_props: dict) -> None:
    """Raise SchemaViolation if the (type-triple, properties) are invalid."""
    if not is_valid_triple(src_type, rel, tgt_type):
        raise SchemaViolation(
            f"invalid triple: ({src_type})-[{rel}]->({tgt_type})"
        )
    missing = REQUIRED_EDGE_FIELDS - edge_props.keys()
    if missing:
        raise SchemaViolation(
            f"edge missing required fields: {sorted(missing)}"
        )
    conf = edge_props["confidence"]
    if not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
        raise SchemaViolation(
            f"edge confidence must be in [0,1], got {conf!r}"
        )
    method = edge_props["extraction_method"]
    if method not in ALLOWED_EXTRACTION_METHODS:
        raise SchemaViolation(
            f"edge extraction_method {method!r} not in "
            f"{sorted(ALLOWED_EXTRACTION_METHODS)}"
        )
    # valid_from must be ISO date; valid_to may be None.
    vf = edge_props["valid_from"]
    if not isinstance(vf, str) or len(vf) < 10:
        raise SchemaViolation(f"edge valid_from must be ISO date, got {vf!r}")
    vt = edge_props["valid_to"]
    if vt is not None and (not isinstance(vt, str) or len(vt) < 10):
        raise SchemaViolation(
            f"edge valid_to must be ISO date or null, got {vt!r}"
        )
    # source_ref: must be a dict identifying the evidence.
    sr = edge_props["source_ref"]
    if not isinstance(sr, dict) or "doc_id" not in sr:
        raise SchemaViolation(
            "edge source_ref must be a dict with at least 'doc_id'"
        )
