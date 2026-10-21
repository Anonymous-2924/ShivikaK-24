"""Structural dispatch: parameterised Cypher over Neo4j.

First-class case (the brief's own words): "given an event or supplier
disruption, which SKUs are reachable and through what paths." Returns
structured path records — plain dicts/lists of scalars — never raw
neo4j ``Node``/``Path`` objects, so callers (and tests, with a fake
driver) never need the neo4j driver installed to consume the result.

Takes a bare ``driver`` (the object returned by
``neo4j.GraphDatabase.driver(...)``), not ``Neo4jWriter`` — this is a
read path and should not create constraints as a side effect.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

DEFAULT_HOPS = 3
DEFAULT_LIMIT = 50


@dataclass
class PathRecord:
    target_id: str
    target_type: str
    hops: int
    path_nodes: list[dict]      # [{"id": ..., "labels": [...]}, ...]
    path_rels: list[dict]       # [{"type": ..., "confidence": ..., ...}, ...]


def find_entity_id(driver, name_hint: str, *, database: str = "neo4j") -> str | None:
    """Best-effort free-text -> node id lookup. Tries exact id match first,
    then a case-insensitive substring match on ``name``. Heuristic — Phase 5
    does not re-run full ER against the query text."""
    with driver.session(database=database) as session:
        rows = session.run(
            "MATCH (n) WHERE n.id = $q "
            "RETURN n.id AS id LIMIT 1",
            q=name_hint,
        )
        for row in rows:
            return row["id"]
        rows = session.run(
            "MATCH (n) WHERE n.name IS NOT NULL "
            "AND toLower(n.name) CONTAINS toLower($q) "
            "RETURN n.id AS id LIMIT 1",
            q=name_hint,
        )
        for row in rows:
            return row["id"]
    return None


def exposure_paths(driver, entity_id: str, *, target_label: str = "SKU",
                    max_hops: int = DEFAULT_HOPS, as_of: str | None = None,
                    limit: int = DEFAULT_LIMIT,
                    database: str = "neo4j") -> list[PathRecord]:
    """Traverse from ``entity_id`` up to ``max_hops`` away, returning every
    reachable node of type ``target_label`` and the path(s) that reach it.

    ``as_of``, if given, filters edges to those valid on that date
    (``valid_from <= as_of`` and ``valid_to IS NULL OR valid_to >= as_of``).
    ``max_hops`` is an int under our own control (from config / CLI, never
    raw user text) — safe to interpolate into the variable-length pattern,
    which Cypher does not accept as a bound parameter.
    """
    hops = int(max_hops)
    if hops < 1:
        raise ValueError("max_hops must be >= 1")

    where_temporal = ""
    params: dict = {"entity_id": entity_id, "limit": limit}
    if as_of is not None:
        where_temporal = (
            "WHERE ALL(r IN rels WHERE r.valid_from <= $as_of "
            "AND (r.valid_to IS NULL OR r.valid_to >= $as_of)) "
        )
        params["as_of"] = as_of

    cypher = (
        f"MATCH (start {{id: $entity_id}}) "
        f"MATCH p = (start)-[rels*1..{hops}]-(tgt:{target_label}) "
        f"{where_temporal}"
        "WITH tgt, p, rels "
        "RETURN tgt.id AS target_id, "
        "       labels(tgt)[0] AS target_type, "
        "       length(p) AS hops, "
        "       [n IN nodes(p) | {id: n.id, labels: labels(n)}] AS path_nodes, "
        "       [r IN rels | {type: type(r), confidence: r.confidence, "
        "                     extraction_method: r.extraction_method, "
        "                     source_ref: r.source_ref, "
        "                     valid_from: r.valid_from, valid_to: r.valid_to}] "
        "         AS path_rels "
        "ORDER BY hops ASC "
        "LIMIT $limit"
    )
    out: list[PathRecord] = []
    with driver.session(database=database) as session:
        for row in session.run(cypher, **params):
            out.append(PathRecord(
                target_id=row["target_id"],
                target_type=row["target_type"] or target_label,
                hops=int(row["hops"]),
                path_nodes=list(row["path_nodes"]),
                path_rels=[_decode_source_ref(r) for r in row["path_rels"]],
            ))
    return out


def _decode_source_ref(rel: dict) -> dict:
    """``source_ref`` is written to Neo4j as a JSON string (Cypher
    properties can't hold a nested map — see
    ``src.graph.writer._neo4j_safe_props``). Decode it back to a dict
    here so callers (``src.retrieve.combine``) see the same shape the
    extractor/builder produced."""
    sr = rel.get("source_ref")
    if isinstance(sr, str):
        try:
            rel = {**rel, "source_ref": json.loads(sr)}
        except json.JSONDecodeError:
            pass
    return rel
