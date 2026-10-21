"""Merge store: non-destructive mapping + unmerge + review queue."""
from __future__ import annotations

from pathlib import Path

from src.resolve.merges import Merge, MergeStore


def test_merge_resolve_and_unmerge(tmp_path: Path) -> None:
    store = MergeStore(tmp_path / "merges.sqlite")
    store.record_merge(Merge(source_id="B", canonical_id="A",
                              score=0.95, evidence={"test": True},
                              created_by="auto"))
    assert store.resolve("A") == "A"
    assert store.resolve("B") == "A"

    # Transitive: C -> B -> A, so resolve(C) == A.
    store.record_merge(Merge(source_id="C", canonical_id="B",
                              score=0.95, evidence={"test": True},
                              created_by="auto"))
    assert store.resolve("C") == "A"

    # Unmerge B -> A. C still points at B, which now resolves to itself.
    n = store.unmerge("B")
    assert n == 1
    assert store.resolve("B") == "B"
    assert store.resolve("C") == "B"   # C still points at B

    # Unmerge C.
    assert store.unmerge("C") == 1
    assert store.resolve("C") == "C"


def test_unmerge_is_idempotent(tmp_path: Path) -> None:
    store = MergeStore(tmp_path / "merges.sqlite")
    store.record_merge(Merge(source_id="B", canonical_id="A",
                              score=0.95, evidence={},
                              created_by="auto"))
    store.unmerge("B")
    assert store.unmerge("B") == 0   # already reversed


def test_review_queue_dedupe_and_resolve(tmp_path: Path) -> None:
    store = MergeStore(tmp_path / "merges.sqlite")
    rid1 = store.enqueue_review("L", "R", 0.85, {"evidence": "x"})
    rid2 = store.enqueue_review("L", "R", 0.85, {"evidence": "x"})
    assert rid1 is not None
    assert rid2 is None   # unique-constraint dedupe

    pending = store.pending_reviews()
    assert len(pending) == 1
    store.resolve_review(pending[0].id, "merge")
    assert store.pending_reviews() == []


def test_review_rejects_bad_verdict(tmp_path: Path) -> None:
    store = MergeStore(tmp_path / "merges.sqlite")
    rid = store.enqueue_review("L", "R", 0.8, {})
    try:
        store.resolve_review(rid, "something_else")
    except ValueError:
        pass
    else:
        raise AssertionError("resolve_review should reject bad verdict")
