"""Reverse a prior merge. Skeleton only in Phase 1.

Phase 4 will fill this in: looks up the merge record in the mapping layer
and removes it. Source entities are untouched because merges are
non-destructive by design.
"""
from __future__ import annotations

import sys


def main(entity_id: str) -> None:
    print(f"[not implemented in Phase 1] unmerge({entity_id!r}) lands in Phase 4.",
          file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
