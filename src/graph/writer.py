"""Neo4j writer with schema-enforced upserts.

Idempotent via MERGE on (type, id). Edges MERGE on
(src, rel, tgt, source_ref.doc_id) so re-running does not duplicate.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from src.graph.schema import validate_edge

_PRIMITIVE_TYPES = (str, int, float, bool, type(None))


def _neo4j_safe_props(props: dict) -> dict:
    """Neo4j property values must be a primitive or an array of
    primitives — never a nested map (e.g. ``source_ref``) or a list
    containing one. JSON-encode anything that isn't already safe, so the
    original dict (what ``validate_edge``/``validate_node`` check) stays
    untouched and only the write path is affected."""
    safe: dict = {}
    for k, v in props.items():
        if isinstance(v, _PRIMITIVE_TYPES):
            safe[k] = v
        elif isinstance(v, list) and all(isinstance(x, _PRIMITIVE_TYPES) for x in v):
            safe[k] = v
        else:
            safe[k] = json.dumps(v, sort_keys=True, default=str)
    return safe


@dataclass(frozen=True)
class Node:
    type: str      # must be in ALLOWED_NODE_TYPES
    id: str
    props: dict


@dataclass(frozen=True)
class Edge:
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    rel_type: str
    props: dict    # must contain required_edge_fields


class Neo4jWriter:
    def __init__(self, *, uri: str, user: str, password: str,
                 database: str = "neo4j") -> None:
        from neo4j import GraphDatabase
        self.database = database
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def ensure_constraints(self) -> None:
        """Node-id uniqueness per type. Idempotent."""
        from src.extract.prompts import ALLOWED_NODE_TYPES
        with self.driver.session(database=self.database) as session:
            for t in ALLOWED_NODE_TYPES:
                session.run(
                    f"CREATE CONSTRAINT {t.lower()}_id_unique IF NOT EXISTS "
                    f"FOR (n:{t}) REQUIRE n.id IS UNIQUE"
                )

    def upsert_nodes(self, nodes: Iterable[Node]) -> int:
        n = 0
        with self.driver.session(database=self.database) as session:
            for node in nodes:
                session.run(
                    f"MERGE (n:{node.type} {{id: $id}}) "
                    f"SET n += $props",
                    id=node.id, props=_neo4j_safe_props(node.props),
                )
                n += 1
        return n

    def upsert_edges(self, edges: Iterable[Edge]) -> tuple[int, int]:
        """Returns (written, rejected). Rejected edges are the ones that
        failed schema validation — they do NOT reach Neo4j."""
        written = rejected = 0
        with self.driver.session(database=self.database) as session:
            for e in edges:
                try:
                    validate_edge(e.source_type, e.rel_type,
                                  e.target_type, e.props)
                except Exception:   # noqa: BLE001
                    rejected += 1
                    continue
                # MERGE key includes doc_id so the same assertion from the
                # same evidence is one edge; different evidence makes a new
                # edge (confidence can then blend/aggregate in Phase 5).
                doc_id = e.props["source_ref"]["doc_id"]
                session.run(
                    f"MATCH (a:{e.source_type} {{id: $sid}}), "
                    f"      (b:{e.target_type} {{id: $tid}}) "
                    f"MERGE (a)-[r:{e.rel_type} {{source_doc: $doc_id}}]->(b) "
                    f"SET r += $props",
                    sid=e.source_id, tid=e.target_id, doc_id=doc_id,
                    props=_neo4j_safe_props(e.props),
                )
                written += 1
        return written, rejected
