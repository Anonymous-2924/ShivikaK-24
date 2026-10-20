"""Build the graph from three sources, in this order of precedence:

1. STRUCTURED ERP exports (JSON/XML suppliers_export, plants_export,
   routes_export, components_export) — high confidence,
   extraction_method='structured'.
2. GOLD data cards in processed/numeric/ — manual, confidence=1.0,
   gets has_financials edges from the supplier/plant to a DataTable node.
3. LLM-EXTRACTED relations from extractions.jsonl — confidence from
   extractor; extraction_method='llm_extracted'.

Node identity across sources uses the resolver (``src.resolve.merges``):
every name/id is passed through ``MergeStore.resolve()`` so merged
entities land on the canonical id. Edges that reference an unresolvable
entity are skipped and counted.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.graph.writer import Edge, Neo4jWriter, Node
from src.resolve.merges import MergeStore


@dataclass
class BuildStats:
    nodes_upserted: int = 0
    edges_written: int = 0
    edges_rejected_schema: int = 0
    edges_skipped_unresolved: int = 0
    sources_processed: int = 0


def build_from_structured(
    *, writer: Neo4jWriter, resolver: MergeStore,
    structured_json_dir: Path, log_fn=print,
) -> BuildStats:
    """Read suppliers/plants/routes/components exports and write them to Neo4j.

    These are deterministic, high-confidence edges. Confidence is set to
    0.98 (not 1.0 — the exports can still have stale rows; gold is 1.0).
    """
    stats = BuildStats()
    nodes: list[Node] = []
    edges: list[Edge] = []

    # Suppliers
    sup_path = structured_json_dir / "suppliers_export.json"
    if sup_path.exists():
        stats.sources_processed += 1
        data = json.loads(sup_path.read_text())
        for s in data.get("suppliers", []):
            canonical = resolver.resolve(s["id"])
            nodes.append(Node(type="Supplier", id=canonical, props={
                "name": s.get("name"),
                "tier": s.get("tier"),
                "country_code": s.get("country_code"),
                "tax_id": s.get("tax_id"),
                "currency": s.get("currency"),
            }))
            # located_in -> Geography (by country code).
            geo_id = f"GEO-{s.get('country_code', 'XX')}"
            nodes.append(Node(type="Geography", id=geo_id,
                              props={"country_code": s.get("country_code"),
                                     "name": s.get("country")}))
            edges.append(_edge(
                "Supplier", canonical, "Geography", geo_id, "located_in",
                confidence=0.98, source_doc=sup_path.name,
                method="structured",
            ))

    # Plants
    plt_path = structured_json_dir / "plants_export.xml"
    if plt_path.exists():
        # The XML writer in Phase 2 stored plants with (SupplierId, CountryCode).
        from xml.etree.ElementTree import parse as _xml_parse
        stats.sources_processed += 1
        root = _xml_parse(plt_path).getroot()
        for p in root.findall("Plant"):
            pid = resolver.resolve(p.attrib.get("id", ""))
            sid = resolver.resolve((p.findtext("SupplierId") or "").strip())
            cc = (p.findtext("CountryCode") or "").strip()
            nodes.append(Node(type="Plant", id=pid, props={
                "name": p.findtext("Name") or "",
                "country_code": cc, "city": p.findtext("City") or "",
            }))
            if sid:
                # Supplier owns plant: manufactured_at goes SKU->Plant (we
                # don't have that from this export alone), but we can state
                # the plant is supplied by its parent supplier.
                edges.append(_edge(
                    "Plant", pid, "Supplier", sid, "supplied_by",
                    confidence=0.98, source_doc=plt_path.name,
                    method="structured",
                ))
            if cc:
                geo_id = f"GEO-{cc}"
                nodes.append(Node(type="Geography", id=geo_id,
                                   props={"country_code": cc}))
                edges.append(_edge(
                    "Plant", pid, "Geography", geo_id, "located_in",
                    confidence=0.98, source_doc=plt_path.name,
                    method="structured",
                ))

    # Routes
    rt_path = structured_json_dir / "routes_export.json"
    if rt_path.exists():
        stats.sources_processed += 1
        data = json.loads(rt_path.read_text())
        for r in data.get("routes", []):
            rid = resolver.resolve(r["route_id"])
            nodes.append(Node(type="Route", id=rid, props={
                "origin_port": r.get("origin_port"),
                "dest_port": r.get("dest_port"),
                "mode": r.get("mode"),
                "transit_days": r.get("transit_days"),
                "carrier": r.get("carrier"),
            }))
            # Port nodes + ships_via edges.
            origin_port_id = f"PORT-{(r.get('origin_port') or '').upper().replace(' ', '_')}"
            nodes.append(Node(type="Port", id=origin_port_id, props={
                "name": r.get("origin_port"),
                "country": r.get("origin_country"),
            }))
            edges.append(_edge(
                "Route", rid, "Port", origin_port_id, "ships_via",
                confidence=0.98, source_doc=rt_path.name,
                method="structured",
            ))

    # Components
    cmp_path = structured_json_dir / "components_export.json"
    if cmp_path.exists():
        stats.sources_processed += 1
        data = json.loads(cmp_path.read_text())
        for c in data.get("components", []):
            cid = resolver.resolve(c["id"])
            primary = resolver.resolve(c.get("primary_supplier") or "")
            nodes.append(Node(type="Component", id=cid, props={
                "kind": c.get("kind"),
                "description": c.get("description"),
                "unit": c.get("unit"),
                "unit_cost_usd": c.get("unit_cost_usd"),
            }))
            if primary:
                edges.append(_edge(
                    "Component", cid, "Supplier", primary, "supplied_by",
                    confidence=0.98, source_doc=cmp_path.name,
                    method="structured",
                ))

    log_fn(f"[build] structured: {len(nodes)} nodes, {len(edges)} edges")
    stats.nodes_upserted += writer.upsert_nodes(_dedupe_nodes(nodes))
    w, rej = writer.upsert_edges(edges)
    stats.edges_written += w
    stats.edges_rejected_schema += rej
    return stats


def load_name_to_id_map(structured_json_dir: Path) -> dict[str, str]:
    """Build a best-effort entity-NAME -> structured-id map from the ERP
    exports, so LLM-extracted relations (which reference entities by the
    name string that appeared in the narrative) can be resolved onto the
    same node ids the structured track uses.

    This is a name-matching heuristic, not an ER pass: it maps each
    export's human-readable field (supplier/plant name, component
    description, route id) to its id, case-sensitively and verbatim. A
    name that doesn't appear in any export (e.g. an alias the LLM saw in
    prose but the ERP never recorded) will not resolve — those edges are
    counted as ``edges_skipped_unresolved`` by the caller, same as today.
    """
    mapping: dict[str, str] = {}

    sup_path = structured_json_dir / "suppliers_export.json"
    if sup_path.exists():
        data = json.loads(sup_path.read_text())
        for s in data.get("suppliers", []):
            if s.get("name") and s.get("id"):
                mapping[s["name"]] = s["id"]

    sku_path = structured_json_dir / "skus_export.json"
    if sku_path.exists():
        data = json.loads(sku_path.read_text())
        for k in data.get("skus", []):
            if k.get("style_number") and k.get("sku_id"):
                mapping[k["style_number"]] = k["sku_id"]
            if k.get("sku_id"):
                mapping[k["sku_id"]] = k["sku_id"]

    plt_path = structured_json_dir / "plants_export.xml"
    if plt_path.exists():
        from xml.etree.ElementTree import parse as _xml_parse
        root = _xml_parse(plt_path).getroot()
        for p in root.findall("Plant"):
            name = p.findtext("Name")
            pid = p.attrib.get("id")
            if name and pid:
                mapping[name] = pid

    rt_path = structured_json_dir / "routes_export.json"
    if rt_path.exists():
        data = json.loads(rt_path.read_text())
        for r in data.get("routes", []):
            if r.get("route_id"):
                mapping[r["route_id"]] = r["route_id"]

    cmp_path = structured_json_dir / "components_export.json"
    if cmp_path.exists():
        data = json.loads(cmp_path.read_text())
        for c in data.get("components", []):
            if c.get("description") and c.get("id"):
                mapping[c["description"]] = c["id"]
            if c.get("id"):
                mapping[c["id"]] = c["id"]

    return mapping


def build_from_extractions(
    *, writer: Neo4jWriter, resolver: MergeStore,
    extractions_path: Path, name_to_id: dict[str, str],
    log_fn=print,
) -> BuildStats:
    """Fold LLM-extracted relations into the graph.

    name_to_id lets us map the LLM-visible entity NAMES back to the
    structured ids (Supplier name → SUP-T1-0001). Names that don't map
    are skipped.
    """
    stats = BuildStats()
    if not extractions_path.exists():
        return stats
    nodes: list[Node] = []
    edges: list[Edge] = []
    for line in extractions_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        doc_id = rec.get("source_file", "unknown")
        for rel in rec.get("relations", []):
            src_name = rel.get("source", "")
            tgt_name = rel.get("target", "")
            src_id = name_to_id.get(src_name)
            tgt_id = name_to_id.get(tgt_name)
            if not src_id or not tgt_id:
                stats.edges_skipped_unresolved += 1
                continue
            src_id = resolver.resolve(src_id)
            tgt_id = resolver.resolve(tgt_id)
            # The entity types the LLM saw aren't stored on the relation
            # itself; look them up via the entities list in this record.
            src_type = _type_for_name(rec.get("entities", []), src_name)
            tgt_type = _type_for_name(rec.get("entities", []), tgt_name)
            if not src_type or not tgt_type:
                stats.edges_skipped_unresolved += 1
                continue
            edges.append(Edge(
                source_type=src_type, source_id=src_id,
                target_type=tgt_type, target_id=tgt_id,
                rel_type=rel["type"],
                props={
                    "confidence": rel.get("confidence", 0.5),
                    "valid_from": "2026-01-01",   # defaults; Phase 5 can refine
                    "valid_to": None,
                    "source_ref": {
                        "doc_id": doc_id,
                        "chunk_index": rec.get("chunk_index"),
                        "evidence_text": rel.get("evidence_text"),
                    },
                    "extraction_method": "llm_extracted",
                    "verified": bool(rel.get("verified", False)),
                },
            ))
    log_fn(f"[build] extractions: {len(nodes)} nodes, {len(edges)} edges, "
           f"skipped {stats.edges_skipped_unresolved} unresolved")
    stats.nodes_upserted += writer.upsert_nodes(_dedupe_nodes(nodes))
    w, rej = writer.upsert_edges(edges)
    stats.edges_written += w
    stats.edges_rejected_schema += rej
    return stats


def build_from_data_cards(
    *, writer: Neo4jWriter, resolver: MergeStore,
    numeric_dir: Path, log_fn=print,
) -> BuildStats:
    """DataTable nodes + has_financials edges from gold schema sidecars.

    This is also where Phase 5's quantitative router finds its parquet
    paths — via Neo4j to the DataTable node, then to its parquet URL
    property.
    """
    stats = BuildStats()
    nodes: list[Node] = []
    edges: list[Edge] = []
    for card_md in numeric_dir.glob("*.md"):
        parquet = card_md.with_suffix(".parquet")
        if not parquet.exists():
            continue
        node_id = f"TBL-{card_md.stem}"
        nodes.append(Node(type="DataTable", id=node_id, props={
            "parquet_path": str(parquet),
            "card_path": str(card_md),
        }))
        # If the data card's linked entity is a Supplier id we recognise,
        # emit a has_financials edge.
        linked = _parse_linked_entity_from_card(card_md.read_text())
        if linked and linked.startswith("Supplier:"):
            sid = resolver.resolve(linked.split(":", 1)[1].strip())
            edges.append(_edge(
                "Supplier", sid, "DataTable", node_id, "has_financials",
                confidence=1.0, source_doc=card_md.name,
                method="manual",
            ))
    log_fn(f"[build] data cards: {len(nodes)} nodes, {len(edges)} edges")
    stats.nodes_upserted += writer.upsert_nodes(nodes)
    w, rej = writer.upsert_edges(edges)
    stats.edges_written += w
    stats.edges_rejected_schema += rej
    return stats


# ---------- helpers ----------
def _edge(src_type: str, src_id: str, tgt_type: str, tgt_id: str,
          rel: str, *, confidence: float, source_doc: str,
          method: str, valid_from: str = "2026-01-01",
          valid_to: str | None = None) -> Edge:
    return Edge(
        source_type=src_type, source_id=src_id,
        target_type=tgt_type, target_id=tgt_id,
        rel_type=rel,
        props={
            "confidence": confidence,
            "valid_from": valid_from, "valid_to": valid_to,
            "source_ref": {"doc_id": source_doc},
            "extraction_method": method,
        },
    )


def _type_for_name(entities: list[dict], name: str) -> str | None:
    for e in entities:
        if e.get("name") == name:
            return e.get("type")
    return None


def _parse_linked_entity_from_card(md: str) -> str | None:
    for line in md.splitlines():
        if line.startswith("- **Linked entities:**"):
            return line.split(":**", 1)[1].strip().split(",")[0].strip()
    return None


def _dedupe_nodes(nodes: Iterable[Node]) -> list[Node]:
    """Last write wins per (type, id). Preserves order of first appearance."""
    seen: dict[tuple[str, str], Node] = {}
    for n in nodes:
        seen[(n.type, n.id)] = n
    return list(seen.values())
