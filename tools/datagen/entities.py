"""Deterministic entity population.

All randomness flows through a single seeded ``random.Random`` so the output
reproduces exactly for a given ``--seed``.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from tools.datagen import domain as dm


# --- Dataclasses ---------------------------------------------------------
@dataclass
class Supplier:
    id: str
    canonical_name: str
    name_variants: list[str]
    tier: int                       # 1 or 2
    country_code: str
    country_name: str
    city: str
    address: str
    tax_id: str
    capabilities: list[str]
    certifications: list[str]
    incoterms: list[str]
    primary_currency: str
    established_year: int
    employees: int
    annual_capacity_units: int      # Tier-1: garments/year. Tier-2: meters or units/year.
    stale: bool = False             # record flagged as stale by the mess injector
    missing_fields: list[str] = field(default_factory=list)


@dataclass
class Plant:
    id: str
    supplier_id: str
    name: str
    country_code: str
    city: str
    address: str
    lines: int                      # production lines
    monthly_capacity_units: int
    cert_subset: list[str]


@dataclass
class Component:
    id: str
    kind: str                       # "fabric" | "trim" | "dye"
    description: str
    unit: str                       # "m", "kg", "pc"
    unit_cost_usd: float
    primary_supplier_id: str        # a tier-2 supplier
    alt_supplier_ids: list[str]


@dataclass
class SKU:
    id: str                         # e.g. "TSH-SS26-NVY-M"
    style_number: str
    garment_type: str
    garment_code: str
    fit: str
    color_name: str
    color_code: str
    size: str
    season: str
    retail_price_usd: float
    cost_target_usd: float
    tier1_supplier_id: str
    plant_id: str
    bom: list[tuple[str, float]]    # (component_id, qty_per_unit)


@dataclass
class Route:
    id: str
    origin_port: str
    origin_country: str
    dest_port: str
    dest_country: str
    mode: str                       # "sea" | "air"
    transit_days: int
    carrier: str


@dataclass
class Pop:
    """Full entity population."""
    suppliers: list[Supplier]
    plants: list[Plant]
    components: list[Component]
    skus: list[SKU]
    routes: list[Route]


# --- Generators ----------------------------------------------------------
def _supplier_name(rng: random.Random, tier: int) -> str:
    stem = rng.choice(dm.SUPPLIER_NAME_STEMS)
    suffix = rng.choice(dm.SUPPLIER_NAME_SUFFIXES)
    if tier == 2 and rng.random() < 0.4:
        # Tier-2 names lean more toward mills / dyeing houses.
        suffix = rng.choice(["Mills", "Weaving", "Spinning Mills",
                             "Dyeing & Finishing", "Textiles",
                             "Trim Co.", "Button Works", "Zipper Industries"])
    return f"{stem} {suffix}"


def _address(rng: random.Random, city: str, country: str) -> str:
    plot = rng.randint(1, 450)
    road = rng.choice(["Road", "Street", "Avenue", "Industrial Area",
                       "Export Processing Zone", "Lane"])
    sector = rng.choice(["Sector", "Block", "Zone", "Phase"])
    sector_no = rng.randint(1, 15)
    return f"Plot {plot}, {sector} {sector_no}, {city} {road}, {country}"


def _tax_id(rng: random.Random, cc: str) -> str:
    return f"{cc}-{rng.randint(10, 99)}-{rng.randint(100000, 999999)}"


def _name_variants(rng: random.Random, canonical: str) -> list[str]:
    """3-5 plausible variants of the same name. Mess injector decides whether
    to actually use them across different documents."""
    stem, _, suffix = canonical.rpartition(" ")
    variants = [canonical]
    # Punctuation / casing drift
    variants.append(canonical.replace(" & ", " and "))
    variants.append(canonical.upper())
    variants.append(f"{stem} {suffix.replace('Pvt Ltd', 'Private Limited')}")
    variants.append(f"{stem.split(' ')[0]} {suffix}")  # just first stem word
    # Dedupe, keep order, trim
    seen: set[str] = set()
    deduped = []
    for v in variants:
        v2 = v.strip()
        if v2 and v2 not in seen:
            seen.add(v2)
            deduped.append(v2)
    return deduped[: rng.randint(3, 5)]


def gen_suppliers(rng: random.Random, n_tier1: int, n_tier2: int) -> list[Supplier]:
    out: list[Supplier] = []
    for i in range(n_tier1):
        country, cc, ccy = rng.choice(dm.COUNTRIES)
        city = rng.choice(dm.PORTS.get(cc, [country])[0:2] + [country + " City"])
        name = _supplier_name(rng, tier=1)
        out.append(Supplier(
            id=f"SUP-T1-{i+1:04d}",
            canonical_name=name,
            name_variants=_name_variants(rng, name),
            tier=1,
            country_code=cc,
            country_name=country,
            city=city,
            address=_address(rng, city, country),
            tax_id=_tax_id(rng, cc),
            capabilities=rng.sample(dm.TIER1_CAPABILITIES,
                                    k=rng.randint(1, len(dm.TIER1_CAPABILITIES))),
            certifications=rng.sample(dm.CERTIFICATIONS,
                                      k=rng.randint(1, 4)),
            incoterms=rng.sample(dm.INCOTERMS, k=rng.randint(1, 3)),
            primary_currency=ccy,
            established_year=rng.randint(1985, 2022),
            employees=rng.randint(80, 6500),
            annual_capacity_units=rng.randint(200_000, 12_000_000),
        ))
    for i in range(n_tier2):
        country, cc, ccy = rng.choice(dm.COUNTRIES)
        city = rng.choice(dm.PORTS.get(cc, [country])[0:2] + [country + " City"])
        name = _supplier_name(rng, tier=2)
        out.append(Supplier(
            id=f"SUP-T2-{i+1:04d}",
            canonical_name=name,
            name_variants=_name_variants(rng, name),
            tier=2,
            country_code=cc,
            country_name=country,
            city=city,
            address=_address(rng, city, country),
            tax_id=_tax_id(rng, cc),
            capabilities=rng.sample(dm.TIER2_CAPABILITIES,
                                    k=rng.randint(1, 3)),
            certifications=rng.sample(dm.CERTIFICATIONS, k=rng.randint(0, 3)),
            incoterms=rng.sample(dm.INCOTERMS, k=rng.randint(1, 2)),
            primary_currency=ccy,
            established_year=rng.randint(1975, 2020),
            employees=rng.randint(40, 2000),
            annual_capacity_units=rng.randint(500_000, 50_000_000),
        ))
    return out


def gen_plants(rng: random.Random, suppliers: list[Supplier], n_plants: int) -> list[Plant]:
    tier1 = [s for s in suppliers if s.tier == 1]
    plants: list[Plant] = []
    i = 0
    while len(plants) < n_plants:
        s = rng.choice(tier1)
        suffix = rng.choice(dm.PLANT_SUFFIXES)
        plants.append(Plant(
            id=f"PLT-{i+1:04d}",
            supplier_id=s.id,
            name=f"{s.canonical_name.split(' ')[0]} {suffix} {len(plants)+1}",
            country_code=s.country_code,
            city=s.city,
            address=_address(rng, s.city, s.country_name),
            lines=rng.randint(2, 24),
            monthly_capacity_units=rng.randint(20_000, 400_000),
            cert_subset=rng.sample(s.certifications,
                                   k=min(len(s.certifications), rng.randint(0, 3))),
        ))
        i += 1
    return plants


def gen_components(rng: random.Random, suppliers: list[Supplier],
                   n_components: int) -> list[Component]:
    tier2 = [s for s in suppliers if s.tier == 2]
    comps: list[Component] = []
    # Fabrics
    n_fab = int(n_components * 0.55)
    for i in range(n_fab):
        fiber = rng.choice(dm.FABRIC_FIBERS)
        gsm = rng.choice([120, 140, 160, 180, 200, 220, 280, 320])
        desc = f"{fiber} knit {gsm} gsm" if "Knit" in fiber or "Jersey" in fiber \
               else f"{fiber} woven {gsm} gsm"
        primary = rng.choice(tier2)
        alts = rng.sample([t.id for t in tier2 if t.id != primary.id],
                          k=min(len(tier2) - 1, rng.randint(0, 3)))
        comps.append(Component(
            id=f"CMP-FAB-{i+1:04d}",
            kind="fabric",
            description=desc,
            unit="m",
            unit_cost_usd=round(rng.uniform(1.8, 14.5), 2),
            primary_supplier_id=primary.id,
            alt_supplier_ids=alts,
        ))
    # Trims
    n_trim = int(n_components * 0.35)
    for i in range(n_trim):
        trim = rng.choice(dm.TRIMS)
        primary = rng.choice(tier2)
        alts = rng.sample([t.id for t in tier2 if t.id != primary.id],
                          k=min(len(tier2) - 1, rng.randint(0, 2)))
        comps.append(Component(
            id=f"CMP-TRM-{i+1:04d}",
            kind="trim",
            description=trim,
            unit="pc",
            unit_cost_usd=round(rng.uniform(0.02, 1.8), 3),
            primary_supplier_id=primary.id,
            alt_supplier_ids=alts,
        ))
    # Dyes / chemicals
    n_dye = n_components - n_fab - n_trim
    for i in range(n_dye):
        dye = rng.choice(dm.DYES_CHEMICALS)
        primary = rng.choice(tier2)
        comps.append(Component(
            id=f"CMP-DYE-{i+1:04d}",
            kind="dye",
            description=dye,
            unit="kg",
            unit_cost_usd=round(rng.uniform(4.0, 48.0), 2),
            primary_supplier_id=primary.id,
            alt_supplier_ids=[],
        ))
    return comps


def _style_number(rng: random.Random) -> str:
    return f"{rng.randint(100, 999)}{rng.choice(['A','B','C','D','E'])}"


def gen_skus(rng: random.Random, suppliers: list[Supplier], plants: list[Plant],
             components: list[Component], n_skus: int) -> list[SKU]:
    tier1 = [s for s in suppliers if s.tier == 1]
    fabrics = [c for c in components if c.kind == "fabric"]
    trims = [c for c in components if c.kind == "trim"]
    dyes = [c for c in components if c.kind == "dye"]

    skus: list[SKU] = []
    i = 0
    while len(skus) < n_skus:
        gtype, gcode = rng.choice(dm.GARMENT_TYPES)
        fit = rng.choice(dm.FITS)
        season = rng.choice(dm.SEASONS)
        style = _style_number(rng)
        # Choose a size run
        run = ("numeric" if gtype in {"Jeans", "Chinos", "Shorts"}
               and rng.random() < 0.6 else "alpha")
        for color_name, color_code in rng.sample(dm.COLORS, k=rng.randint(1, 3)):
            for size in rng.sample(dm.SIZE_RUNS[run], k=rng.randint(3, 5)):
                sku_id = f"{gcode}-{style}-{season}-{color_code}-{size}"
                t1 = rng.choice(tier1)
                plant = rng.choice([p for p in plants if p.supplier_id == t1.id]
                                   or plants)
                # BOM: 1-2 fabrics, 2-5 trims, 0-1 dyes
                bom: list[tuple[str, float]] = []
                for f in rng.sample(fabrics, k=min(len(fabrics), rng.randint(1, 2))):
                    bom.append((f.id, round(rng.uniform(0.4, 3.5), 2)))
                for t in rng.sample(trims, k=min(len(trims), rng.randint(2, 5))):
                    bom.append((t.id, float(rng.randint(1, 8))))
                if dyes and rng.random() < 0.4:
                    d = rng.choice(dyes)
                    bom.append((d.id, round(rng.uniform(0.005, 0.08), 3)))
                retail = round(rng.uniform(9.99, 189.99), 2)
                cost = round(retail * rng.uniform(0.18, 0.42), 2)
                skus.append(SKU(
                    id=sku_id, style_number=style,
                    garment_type=gtype, garment_code=gcode, fit=fit,
                    color_name=color_name, color_code=color_code, size=size,
                    season=season, retail_price_usd=retail, cost_target_usd=cost,
                    tier1_supplier_id=t1.id, plant_id=plant.id, bom=bom,
                ))
                i += 1
                if len(skus) >= n_skus:
                    break
            if len(skus) >= n_skus:
                break
    # Dedupe on id (rare collisions) and trim.
    seen: set[str] = set()
    out: list[SKU] = []
    for s in skus:
        if s.id in seen:
            continue
        seen.add(s.id)
        out.append(s)
        if len(out) >= n_skus:
            break
    return out


def gen_routes(rng: random.Random, n_routes: int) -> list[Route]:
    all_origin: list[tuple[str, str, str]] = []  # (port, country_code, country_name)
    cc_to_name = {cc: name for name, cc, _ in dm.COUNTRIES}
    for cc, ports in dm.PORTS.items():
        for p in ports:
            all_origin.append((p, cc, cc_to_name.get(cc, cc)))
    routes: list[Route] = []
    carriers = ["Maersk", "MSC", "CMA CGM", "Hapag-Lloyd", "ONE",
                "COSCO", "Evergreen", "Yang Ming", "ZIM", "Qatar Airways Cargo"]
    for i in range(n_routes):
        op, ocode, oname = rng.choice(all_origin)
        dp, dcode = rng.choice(dm.DESTINATION_PORTS)
        mode = "air" if rng.random() < 0.15 else "sea"
        if mode == "sea":
            transit = rng.randint(14, 45)
        else:
            transit = rng.randint(2, 6)
        routes.append(Route(
            id=f"RTE-{i+1:04d}", origin_port=op, origin_country=oname,
            dest_port=dp, dest_country=dcode, mode=mode,
            transit_days=transit,
            carrier=rng.choice(carriers),
        ))
    return routes


def populate(rng: random.Random, *, n_tier1: int, n_tier2: int, n_plants: int,
             n_components: int, n_skus: int, n_routes: int) -> Pop:
    suppliers = gen_suppliers(rng, n_tier1, n_tier2)
    plants = gen_plants(rng, suppliers, n_plants)
    components = gen_components(rng, suppliers, n_components)
    skus = gen_skus(rng, suppliers, plants, components, n_skus)
    routes = gen_routes(rng, n_routes)
    return Pop(suppliers=suppliers, plants=plants, components=components,
               skus=skus, routes=routes)


# --- Small helpers used by writers ---------------------------------------
def random_date_in_year(rng: random.Random, year: int) -> date:
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    return start + timedelta(days=rng.randint(0, (end - start).days))
