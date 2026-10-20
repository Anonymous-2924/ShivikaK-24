"""Deliberate mess injection.

Each function mutates its argument *in place* and appends to the realism
log, so the audit shows exactly what the ingest pipeline is supposed to
cope with.
"""
from __future__ import annotations

import random

from tools.datagen.entities import Pop, Supplier
from tools.datagen.realism_log import RealismLog

# ~5% missing fields across suppliers; ~3% stale records.
MISSING_FIELD_RATE = 0.05
STALE_RATE = 0.03
# Fraction of suppliers that will have a near-duplicate entry injected into
# the master lists (same company, slightly different address + name variant).
DUPLICATE_SUPPLIER_RATE = 0.02


def flag_missing_fields(pop: Pop, rng: random.Random, log: RealismLog) -> None:
    maskable = ["tax_id", "address", "primary_currency", "incoterms"]
    for s in pop.suppliers:
        if rng.random() < MISSING_FIELD_RATE:
            field = rng.choice(maskable)
            s.missing_fields.append(field)
            log.event(
                "supplier.missing_field",
                f"{s.id} ({s.canonical_name}): missing {field}",
            )


def flag_stale(pop: Pop, rng: random.Random, log: RealismLog) -> None:
    for s in pop.suppliers:
        if rng.random() < STALE_RATE:
            s.stale = True
            log.event(
                "supplier.stale_record",
                f"{s.id} ({s.canonical_name}): last-verified >3 years ago",
            )


def inject_near_duplicate_suppliers(pop: Pop, rng: random.Random,
                                    log: RealismLog) -> list[Supplier]:
    """Return a list of *extra* supplier rows to append to the master
    export: same company, slightly different address, different name
    variant. The ER review queue should flag these as review-bucket pairs.
    """
    dupes: list[Supplier] = []
    for s in list(pop.suppliers):
        if rng.random() >= DUPLICATE_SUPPLIER_RATE:
            continue
        variant = (s.name_variants[-1] if len(s.name_variants) > 1
                   else s.canonical_name)
        # tweak address: add a wing or alter a plot number by ±2
        parts = s.address.split(",")
        if parts and parts[0].strip().lower().startswith("plot"):
            try:
                plot_no = int(parts[0].split()[1]) + rng.choice([-2, -1, 1, 2])
                parts[0] = f"Plot {plot_no}"
            except (ValueError, IndexError):
                parts[0] = parts[0] + " Wing B"
        new_addr = ",".join(parts)
        dup_id = s.id + "-DUP"
        dupes.append(Supplier(
            id=dup_id,
            canonical_name=variant,
            name_variants=[variant],
            tier=s.tier,
            country_code=s.country_code,
            country_name=s.country_name,
            city=s.city,
            address=new_addr,
            # Deliberately keep the SAME tax_id — this is the structural
            # signal the ER should pick up.
            tax_id=s.tax_id,
            capabilities=s.capabilities,
            certifications=s.certifications,
            incoterms=s.incoterms,
            primary_currency=s.primary_currency,
            established_year=s.established_year,
            employees=s.employees,
            annual_capacity_units=s.annual_capacity_units,
        ))
        log.event(
            "duplicate.near_duplicate_supplier",
            f"{dup_id} is a near-duplicate of {s.id} "
            f"({s.canonical_name} vs {variant}); shared tax_id {s.tax_id}",
        )
    return dupes


def pick_name_variant(rng: random.Random, s: Supplier, log: RealismLog,
                      *, context: str) -> str:
    """Return one of this supplier's name variants, with a note that this
    document used a non-canonical spelling. The ER test corpus relies on
    these being tracked.
    """
    variant = rng.choice(s.name_variants)
    if variant != s.canonical_name:
        log.event(
            "name.variant_used",
            f"{context}: '{variant}' used for {s.id} "
            f"(canonical: '{s.canonical_name}')",
        )
    return variant


def ocr_noise(text: str, rng: random.Random, log: RealismLog, *,
              context: str) -> str:
    """Introduce OCR-style character swaps across a short passage.

    Covers single-char lookalikes (l/1, I/1, O/0, S/5, B/8, Z/2, G/6, e/c)
    and the two-char ``rn``/``m`` confusion, which is the classic PDF-OCR
    artefact. We mutate the string character by character so swap frequency
    scales with how many lookalike characters the text actually contains.
    """
    single: dict[str, str] = {
        "l": "1", "I": "1", "O": "0", "S": "5", "B": "8",
        "Z": "2", "G": "6", "e": "c", "o": "0", "i": "l",
    }
    chars = list(text)
    changes = 0
    i = 0
    while i < len(chars):
        # Two-char swap first.
        if i + 1 < len(chars) and chars[i] == "r" and chars[i + 1] == "n":
            if rng.random() < 0.5:
                chars[i] = "m"
                del chars[i + 1]
                changes += 1
                i += 1
                continue
        if chars[i] in single and rng.random() < 0.15:
            chars[i] = single[chars[i]]
            changes += 1
        i += 1
    if changes:
        log.bump("text.ocr_noise")
        log.event("text.ocr_noise_sample",
                  f"{context}: {changes} chars perturbed")
    return "".join(chars)


def mixed_units_price(rng: random.Random, usd_price: float, currency: str,
                      log: RealismLog, *, context: str) -> tuple[float, str]:
    """Occasionally re-denominate a USD price into the supplier's local
    currency WITHOUT labelling it clearly. The ingest pipeline should pick
    this up as a validator warning."""
    rough_fx = {
        "BDT": 110, "VND": 24500, "INR": 83, "CNY": 7.2, "TRY": 34,
        "EUR": 0.92, "KHR": 4100, "IDR": 15500, "PKR": 280, "LKR": 300,
        "MAD": 10, "TND": 3.1, "MXN": 17, "HNL": 25, "PEN": 3.8,
        "EGP": 48, "MMK": 2100, "ETB": 56, "USD": 1.0,
    }
    if currency == "USD" or rng.random() < 0.9:
        return usd_price, "USD"
    fx = rough_fx.get(currency, 1.0)
    local = round(usd_price * fx, 2)
    log.event("units.unlabelled_currency",
              f"{context}: price written in {currency} but labelled as USD "
              f"({usd_price} USD -> {local} {currency})")
    return local, currency   # The USD label is applied by the caller.


def inject_contradiction(pop: Pop, rng: random.Random, log: RealismLog,
                         n: int = 10) -> list[tuple[str, str]]:
    """Pick N suppliers whose capacity will be reported differently in two
    sources. Returns the chosen supplier IDs and their 'alternate' capacity.
    Writers that respect this list should use the alternate value.
    """
    chosen = rng.sample(pop.suppliers, k=min(n, len(pop.suppliers)))
    out: list[tuple[str, str]] = []
    for s in chosen:
        alt = int(s.annual_capacity_units * rng.uniform(0.4, 1.8))
        out.append((s.id, str(alt)))
        log.event(
            "contradiction.capacity",
            f"{s.id} ({s.canonical_name}): master = {s.annual_capacity_units}, "
            f"audit = {alt}",
        )
    return out
