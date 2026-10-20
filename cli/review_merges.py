"""Interactive review queue CLI.

Shows candidate pairs that fell in the middle band of ER scoring, one at
a time, with the evidence that put them there. Accepts y / n / s (skip)
/ q (quit). y records a merge; n permanently rejects; s leaves it in the
queue; q exits cleanly.
"""
from __future__ import annotations

import sys
from pathlib import Path

from src.resolve.merges import Merge, MergeStore

MERGES_SQLITE = Path("data/processed/merges.sqlite")


def main() -> None:
    store = MergeStore(MERGES_SQLITE)
    pending = store.pending_reviews()
    if not pending:
        print("Review queue is empty.")
        return
    print(f"{len(pending)} candidate pair(s) in the review queue.")
    print(f"Store: {MERGES_SQLITE}")
    print("Keys: y=merge, n=reject, s=skip (leave in queue), q=quit\n")
    for i, cand in enumerate(pending, start=1):
        print(f"--- {i}/{len(pending)}  score={cand.score:.3f} ---")
        print(f"  LEFT  : {cand.left_id}")
        print(f"  RIGHT : {cand.right_id}")
        for k, v in sorted(cand.evidence.items()):
            print(f"    {k}: {v}")
        try:
            resp = input("merge? [y/n/s/q] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n(quit)")
            break
        if resp in {"y", "yes"}:
            # Pick the LEFT as canonical by convention — the user can
            # unmerge and re-merge the other way if they prefer.
            store.record_merge(Merge(
                source_id=cand.right_id, canonical_id=cand.left_id,
                score=cand.score, evidence=cand.evidence,
                created_by="review",
            ))
            store.resolve_review(cand.id, "merge")
            print(f"  merged {cand.right_id} -> {cand.left_id}")
        elif resp in {"n", "no"}:
            store.resolve_review(cand.id, "reject")
            print("  rejected")
        elif resp in {"q", "quit"}:
            print("  (quit; remaining pairs stay in queue)")
            break
        else:
            store.resolve_review(cand.id, "skip")
            print("  skipped (stays in queue)")
    store.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
