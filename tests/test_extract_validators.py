"""Validators: reject-first, vocabulary-conformant, verbatim-only."""
from __future__ import annotations

from src.extract.validators import apply_verifier, validate_entities, validate_relations

CHUNK = (
    "Horizon Textiles ships via Chittagong port to Rotterdam. "
    "The supplier operates a dyeing unit in Dhaka."
)


def test_entities_accepts_verbatim_in_vocab() -> None:
    payload = {"entities": [
        {"name": "Horizon Textiles", "type": "Supplier"},
        {"name": "Chittagong",        "type": "Port"},
        {"name": "Rotterdam",         "type": "Port"},
    ]}
    r = validate_entities(payload, chunk_text=CHUNK)
    assert r.ok and len(r.entities) == 3 and r.dropped == 0


def test_entities_rejects_out_of_vocab_type() -> None:
    r = validate_entities(
        {"entities": [{"name": "Horizon Textiles", "type": "Vendor"}]},
        chunk_text=CHUNK)
    assert r.ok and not r.entities and r.dropped == 1


def test_entities_rejects_hallucinated_names() -> None:
    r = validate_entities(
        {"entities": [{"name": "Phantom Garments Inc", "type": "Supplier"}]},
        chunk_text=CHUNK)
    assert r.dropped == 1 and not r.entities


def test_entities_dedupes() -> None:
    r = validate_entities({"entities": [
        {"name": "Horizon Textiles", "type": "Supplier"},
        {"name": "Horizon Textiles", "type": "Supplier"},
    ]}, chunk_text=CHUNK)
    assert len(r.entities) == 1 and r.dropped == 1


def test_relations_accept_valid_pair() -> None:
    r = validate_relations(
        {"relations": [{
            "source": "Horizon Textiles", "target": "Chittagong",
            "type": "ships_via", "confidence": 0.9,
            "evidence_text": "ships via Chittagong port",
        }]},
        entity_names={"Horizon Textiles", "Chittagong"},
        chunk_text=CHUNK)
    assert r.ok and len(r.relations) == 1
    rel = r.relations[0]
    assert rel["confidence"] == 0.9
    assert rel["evidence_text"] == "ships via Chittagong port"


def test_relations_reject_source_not_in_entities() -> None:
    r = validate_relations(
        {"relations": [{
            "source": "Phantom Co", "target": "Chittagong",
            "type": "ships_via", "confidence": 0.9,
            "evidence_text": "ships via Chittagong port",
        }]},
        entity_names={"Chittagong"},
        chunk_text=CHUNK)
    assert len(r.relations) == 0 and r.dropped == 1


def test_relations_reject_bad_type() -> None:
    r = validate_relations(
        {"relations": [{
            "source": "A", "target": "B",
            "type": "exports_to", "confidence": 0.9,
            "evidence_text": "e",
        }]},
        entity_names={"A", "B"},
        chunk_text=CHUNK)
    assert r.dropped == 1 and not r.relations


def test_apply_verifier_accept_modify_reject() -> None:
    cands = [
        {"source": "A", "target": "B", "type": "supplied_by",
         "confidence": 0.5, "evidence_text": "ev"},
        {"source": "A", "target": "C", "type": "ships_via",
         "confidence": 0.6, "evidence_text": "ev"},
        {"source": "A", "target": "D", "type": "located_in",
         "confidence": 0.5, "evidence_text": "ev"},
    ]
    verifier_payload = {"verified": [
        {"index": 1, "source": "A", "target": "B",
         "type": "supplied_by", "verdict": "accept", "confidence": 0.95},
        {"index": 2, "source": "A", "target": "C",
         "type": "ships_via", "verdict": "reject", "confidence": 0.1},
        {"index": 3, "source": "A", "target": "D",
         "type": "manufactured_at", "verdict": "modify", "confidence": 0.8},
    ]}
    kept = apply_verifier(verifier_payload, cands)
    assert len(kept) == 2
    assert kept[0]["type"] == "supplied_by" and kept[0]["confidence"] == 0.95
    assert kept[0]["verified"] is True
    assert kept[1]["type"] == "manufactured_at"
    assert kept[1]["confidence"] == 0.8


def test_apply_verifier_missing_indices_marked_unverified() -> None:
    cands = [{"source": "A", "target": "B", "type": "supplied_by",
              "confidence": 0.5, "evidence_text": "ev"}]
    # Verifier returned something unparseable — proposer output preserved.
    kept = apply_verifier({"unexpected": "shape"}, cands)
    assert len(kept) == 1 and kept[0]["verified"] is False
