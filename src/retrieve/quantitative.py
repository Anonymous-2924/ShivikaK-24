"""Quantitative dispatch: Neo4j -> DataTable -> DuckDB on the Parquet.

Brief rule for Phase 5: **do not let the LLM write arbitrary SQL** — that
is Phase 7+ territory. This module only ever runs a small, fixed catalog
of pre-written aggregate queries.

The generated corpus has no fixed financial schema (every Excel/CSV sheet
infers its own columns — see ``src/ingest/numeric.py`` and
``tools/datagen/writers/excel.py``), so hardcoding a column name like
``revenue_usd`` would be a guess. Instead each catalog entry *discovers*
a matching column by name pattern against the Parquet's real schema (via
DuckDB's ``information_schema``) and only runs its aggregate if a match
exists — never freeform SQL, never an invented column name.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# name -> (column-name regex, SQL aggregate template, result label)
# {col} and {table} are substituted with an already-validated identifier
# (the discovered column name / the parquet-derived view name) — never
# with request-supplied text.
_CATALOG: dict[str, tuple[re.Pattern, str, str]] = {
    "revenue": (
        re.compile(r"revenue|sales_usd|amount_usd", re.I),
        "SELECT SUM({col}) AS total, AVG({col}) AS average, "
        "COUNT(*) AS n_rows FROM {table} WHERE {col} IS NOT NULL",
        "revenue_usd",
    ),
    "buffer_days": (
        re.compile(r"buffer.?days?|safety.?stock.?days?", re.I),
        "SELECT AVG({col}) AS average, MIN({col}) AS min, "
        "MAX({col}) AS max, COUNT(*) AS n_rows "
        "FROM {table} WHERE {col} IS NOT NULL",
        "buffer_days",
    ),
    "lead_time": (
        re.compile(r"lead.?time|transit.?days?", re.I),
        "SELECT AVG({col}) AS average, MIN({col}) AS min, "
        "MAX({col}) AS max, COUNT(*) AS n_rows "
        "FROM {table} WHERE {col} IS NOT NULL",
        "lead_time_days",
    ),
}


@dataclass
class QuantResult:
    metric: str
    parquet_path: str
    column_used: str | None
    result: dict | None        # None if no matching column was found
    note: str


def find_datatable_for_entity(driver, entity_id: str, *,
                               database: str = "neo4j") -> list[dict]:
    """Supplier/Plant -[has_financials]-> DataTable. Returns a list of
    {"table_id", "parquet_path"} dicts (an entity may have more than one)."""
    with driver.session(database=database) as session:
        rows = session.run(
            "MATCH (e {id: $entity_id})-[:has_financials]->(t:DataTable) "
            "RETURN t.id AS table_id, t.parquet_path AS parquet_path",
            entity_id=entity_id,
        )
        return [{"table_id": r["table_id"], "parquet_path": r["parquet_path"]}
                for r in rows]


def run_metric(conn, parquet_path: str, metric: str) -> QuantResult:
    """``conn`` is a DuckDB connection (``duckdb.connect()``). ``metric``
    must be a key in ``_CATALOG``."""
    if metric not in _CATALOG:
        raise ValueError(f"unknown metric {metric!r}; "
                          f"catalog has: {sorted(_CATALOG)}")
    pattern, sql_template, label = _CATALOG[metric]
    table_expr = "read_parquet(?)"
    columns = [row[0] for row in conn.execute(
        f"DESCRIBE SELECT * FROM {table_expr}", [parquet_path]).fetchall()]
    match = next((c for c in columns if pattern.search(c)), None)
    if match is None:
        return QuantResult(
            metric=metric, parquet_path=parquet_path, column_used=None,
            result=None,
            note=f"no column matching metric {metric!r} found in "
                 f"{parquet_path} (columns: {columns})",
        )
    # match came from the Parquet's own schema (DuckDB-reported column
    # names), never from request text — safe to interpolate.
    sql = sql_template.format(col=f'"{match}"', table=table_expr)
    row = conn.execute(sql, [parquet_path]).fetchone()
    col_names = [d[0] for d in conn.description]
    result = dict(zip(col_names, row, strict=True))
    return QuantResult(
        metric=metric, parquet_path=parquet_path, column_used=match,
        result=result, note=f"matched column {match!r} for metric {label}",
    )
