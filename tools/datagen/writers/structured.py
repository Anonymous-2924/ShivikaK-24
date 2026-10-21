"""ERP-style structured exports: JSON and XML."""
from __future__ import annotations

import json
import random
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

from tools.datagen.entities import Pop
from tools.datagen.realism_log import RealismLog


def write_suppliers_json(path: Path, pop: Pop, extras: list,
                         rng: random.Random, log: RealismLog) -> Path:
    data = {
        "export_from": "ERP-SX7",
        "exported_at": "2026-09-30T23:59:00Z",
        "schema_version": "2.4",
        "suppliers": [
            {
                "id": s.id,
                "name": s.canonical_name,
                "tier": s.tier,
                "country": s.country_name,
                "country_code": s.country_code,
                "tax_id": s.tax_id,
                "capabilities": s.capabilities,
                "certifications": s.certifications,
                "currency": s.primary_currency,
                "annual_capacity_units": s.annual_capacity_units,
                "incoterms": s.incoterms,
                "stale": s.stale,
            }
            for s in (pop.suppliers + extras)
        ],
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def write_skus_json(path: Path, pop: Pop, log: RealismLog) -> Path:
    data = {
        "export_from": "ERP-SX7",
        "exported_at": "2026-09-30T23:59:00Z",
        "skus": [
            {
                "sku_id": k.id,
                "style_number": k.style_number,
                "garment_type": k.garment_type,
                "fit": k.fit,
                "color": k.color_name,
                "size": k.size,
                "season": k.season,
                "retail_price_usd": k.retail_price_usd,
                "cost_target_usd": k.cost_target_usd,
                "tier1_supplier": k.tier1_supplier_id,
                "plant": k.plant_id,
                "bom": [{"component_id": c, "qty": q} for c, q in k.bom],
            }
            for k in pop.skus
        ],
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def write_plants_xml(path: Path, pop: Pop, log: RealismLog) -> Path:
    root = Element("PlantsExport", attrib={
        "source": "ERP-SX7", "schema_version": "2.4",
        "exported_at": "2026-09-30T23:59:00Z",
    })
    for p in pop.plants:
        node = SubElement(root, "Plant", attrib={"id": p.id})
        SubElement(node, "SupplierId").text = p.supplier_id
        SubElement(node, "Name").text = p.name
        SubElement(node, "CountryCode").text = p.country_code
        SubElement(node, "City").text = p.city
        SubElement(node, "Address").text = p.address
        SubElement(node, "Lines").text = str(p.lines)
        SubElement(node, "MonthlyCapacityUnits").text = str(p.monthly_capacity_units)
        certs_node = SubElement(node, "Certifications")
        for c in p.cert_subset:
            SubElement(certs_node, "Certification").text = c
    ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def write_routes_json(path: Path, pop: Pop, log: RealismLog) -> Path:
    data = {
        "export_from": "TMS-R2",
        "exported_at": "2026-09-30T23:59:00Z",
        "routes": [
            {
                "route_id": r.id,
                "origin_port": r.origin_port,
                "origin_country": r.origin_country,
                "dest_port": r.dest_port,
                "dest_country": r.dest_country,
                "mode": r.mode,
                "transit_days": r.transit_days,
                "carrier": r.carrier,
            }
            for r in pop.routes
        ],
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def write_components_json(path: Path, pop: Pop, log: RealismLog) -> Path:
    data = {
        "export_from": "ERP-SX7",
        "components": [
            {
                "id": c.id,
                "kind": c.kind,
                "description": c.description,
                "unit": c.unit,
                "unit_cost_usd": c.unit_cost_usd,
                "primary_supplier": c.primary_supplier_id,
                "alt_suppliers": c.alt_supplier_ids,
            }
            for c in pop.components
        ],
    }
    path.write_text(json.dumps(data, indent=2))
    return path
