"""Schema validator: triples outside the whitelist are rejected
regardless of edge properties."""
from __future__ import annotations

import pytest

from src.graph.schema import SchemaViolation, is_valid_triple, validate_edge

VALID_EDGE_PROPS = {
    "confidence": 0.9,
    "valid_from": "2026-01-01",
    "valid_to": None,
    "source_ref": {"doc_id": "a.pdf"},
    "extraction_method": "llm_extracted",
}


def test_is_valid_triple_whitelist() -> None:
    assert is_valid_triple("Supplier", "located_in", "Geography")
    assert is_valid_triple("SKU", "manufactured_at", "Plant")
    assert is_valid_triple("Component", "supplied_by", "Supplier")


def test_is_valid_triple_rejects_brief_example() -> None:
    # The brief's own example of an invalid triple.
    assert not is_valid_triple("Geography", "supplied_by", "SKU")


def test_is_valid_triple_rejects_unknown_types() -> None:
    assert not is_valid_triple("Vendor", "supplied_by", "Supplier")
    assert not is_valid_triple("Supplier", "exports_to", "Geography")


def test_validate_edge_accepts_well_formed() -> None:
    validate_edge("Supplier", "located_in", "Geography", VALID_EDGE_PROPS)


def test_validate_edge_requires_all_fields() -> None:
    for missing in ("confidence", "valid_from", "valid_to",
                     "source_ref", "extraction_method"):
        props = {k: v for k, v in VALID_EDGE_PROPS.items() if k != missing}
        with pytest.raises(SchemaViolation):
            validate_edge("Supplier", "located_in", "Geography", props)


def test_validate_edge_rejects_bad_confidence() -> None:
    props = {**VALID_EDGE_PROPS, "confidence": 1.5}
    with pytest.raises(SchemaViolation):
        validate_edge("Supplier", "located_in", "Geography", props)


def test_validate_edge_rejects_bad_extraction_method() -> None:
    props = {**VALID_EDGE_PROPS, "extraction_method": "guessed"}
    with pytest.raises(SchemaViolation):
        validate_edge("Supplier", "located_in", "Geography", props)


def test_validate_edge_rejects_invalid_triple() -> None:
    with pytest.raises(SchemaViolation):
        validate_edge("Geography", "supplied_by", "SKU", VALID_EDGE_PROPS)
