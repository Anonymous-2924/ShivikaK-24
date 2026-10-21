"""Generate the ER-evaluation fixture at tests/fixtures/er_pairs.json.

Produces ~200 labelled pairs mixing:
  - 'match'      — same supplier under different name variants / addresses
                   but same tax_id (the generator's near-duplicate mess)
  - 'no_match'   — different suppliers, random pairings
  - 'ambiguous'  — different suppliers that happen to share a country +
                   partial string similarity

Deterministic given --seed. Writes a JSON file the resolver's evaluator
reads directly.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from tools.datagen import domain as dm
from tools.datagen import entities, mess
from tools.datagen.realism_log import RealismLog


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="tests/fixtures/er_pairs.json")
    p.add_argument("--n-match", type=int, default=80)
    p.add_argument("--n-nomatch", type=int, default=80)
    p.add_argument("--n-ambiguous", type=int, default=40)
    args = p.parse_args()

    rng = random.Random(args.seed)
    log = RealismLog()
    # Build a mid-size supplier set from which to draw.
    pop = entities.populate(
        rng, n_tier1=120, n_tier2=50, n_plants=20,
        n_components=100, n_skus=60, n_routes=10,
    )
    mess.flag_missing_fields(pop, rng, log)
    extras = mess.inject_near_duplicate_suppliers(pop, rng, log)

    pairs: list[dict] = []

    # Positive 'match' pairs — generate from each supplier by picking a
    # NAME VARIANT and tweaking the address, keeping the same tax_id.
    # These are the exact shape of mess the ingest should catch as a
    # review-queue or auto-merge candidate.
    tier1 = [s for s in pop.suppliers if s.tier == 1]
    rng.shuffle(tier1)
    for s in tier1[: args.n_match]:
        variants = [v for v in s.name_variants if v != s.canonical_name]
        if not variants:
            continue
        variant = rng.choice(variants)
        tweaked_addr = _tweak_address(s.address, rng)
        synth_id = s.id + "-ALT"
        synth = {
            "id": synth_id, "name": variant, "type": "Supplier",
            "tax_id": s.tax_id, "country_code": s.country_code,
            "address": tweaked_addr,
        }
        pairs.append({"left": _rec(s), "right": synth, "label": "match"})
    _ = extras   # consumed by the pop; kept for stat parity

    # Negative 'no_match' — random cross-country pairs.
    for _ in range(args.n_nomatch):
        a, b = rng.sample(tier1, 2)
        pairs.append({"left": _rec(a), "right": _rec(b), "label": "no_match"})

    # Ambiguous — same country, partial name overlap.
    by_country: dict[str, list] = {}
    for s in tier1:
        by_country.setdefault(s.country_code, []).append(s)
    added = 0
    attempts = 0
    while added < args.n_ambiguous and attempts < args.n_ambiguous * 20:
        attempts += 1
        bucket = rng.choice([b for b in by_country.values() if len(b) >= 2])
        a, b = rng.sample(bucket, 2)
        a_tok = set(a.canonical_name.lower().split())
        b_tok = set(b.canonical_name.lower().split())
        if a_tok & b_tok:
            pairs.append({"left": _rec(a), "right": _rec(b),
                           "label": "ambiguous"})
            added += 1

    rng.shuffle(pairs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "_comment": ("ER evaluation fixture. Labels: match | no_match | "
                     "ambiguous. 'match' pairs share a tax_id. 'no_match' "
                     "pairs are random cross-country. 'ambiguous' pairs "
                     "share a country and have partial name overlap."),
        "pairs": pairs,
    }
    out.write_text(json.dumps(doc, indent=2))
    print(f"wrote {len(pairs)} pairs to {out}")
    _ = dm  # imported for domain-vocab deterministic reproducibility
    return 0


def _tweak_address(addr: str, rng: random.Random) -> str:
    """Shift a plot number by +/-2 or add a wing suffix."""
    parts = addr.split(",")
    if parts and parts[0].strip().lower().startswith("plot"):
        try:
            parts[0] = (
                "Plot "
                + str(int(parts[0].split()[1]) + rng.choice([-2, -1, 1, 2]))
            )
        except (ValueError, IndexError):
            parts[0] = parts[0] + " Wing B"
    return ",".join(parts)


def _rec(s) -> dict:
    return {
        "id": s.id,
        "name": s.canonical_name,
        "type": "Supplier",
        "tax_id": s.tax_id,
        "country_code": s.country_code,
        "address": s.address,
    }


if __name__ == "__main__":
    raise SystemExit(main())
