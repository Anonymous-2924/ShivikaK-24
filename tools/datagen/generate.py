"""Phase 1: skeleton only. Phase 2 fills this in.

CLI contract (locked):
    python -m tools.datagen.generate --suppliers N --skus M --seed S
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    p = argparse.ArgumentParser(prog="tools.datagen.generate")
    p.add_argument("--suppliers", type=int, default=500)
    p.add_argument("--skus", type=int, default=2000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="generated_data")
    args = p.parse_args()

    print(
        f"[not implemented in Phase 1] generate(suppliers={args.suppliers}, "
        f"skus={args.skus}, seed={args.seed}, out={args.out}) lands in Phase 2.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
