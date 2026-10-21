"""Reverse one entity's live merges.

Merges are non-destructive — this flips reversed=1 on every live row
whose source is ``entity_id`` and leaves the history intact. The entity
will next resolve back to itself unless a new merge supersedes.
"""
from __future__ import annotations

import sys
from pathlib import Path

from src.resolve.merges import MergeStore

MERGES_SQLITE = Path("data/processed/merges.sqlite")


def main(entity_id: str) -> None:
    if not entity_id:
        print("usage: python -m cli unmerge <entity_id>", file=sys.stderr)
        sys.exit(2)
    store = MergeStore(MERGES_SQLITE)
    n = store.unmerge(entity_id)
    store.close()
    if n == 0:
        print(f"no live merges found for {entity_id!r}")
    else:
        print(f"reversed {n} merge(s) for {entity_id!r}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
