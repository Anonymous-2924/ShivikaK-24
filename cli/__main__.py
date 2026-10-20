"""Top-level CLI. Phase 1: skeleton only.

Every subcommand is wired so Make targets end-to-end, but each prints a
clear 'not implemented in Phase <n>' and exits non-zero. This is deliberate:
we never want a Make target to appear to succeed when it did nothing.
"""
from __future__ import annotations

import sys

import typer

app = typer.Typer(add_completion=False, help="Supply Chain Blast Radius Engine CLI")


def _not_impl(phase: int, what: str) -> None:
    typer.echo(f"[not yet implemented] {what} lands in Phase {phase}.", err=True)
    sys.exit(2)


@app.command()
def ingest(
    force: bool = typer.Option(
        False, "--force",
        help="Re-process every file even if the audit log says it already "
             "succeeded for this content hash."),
    no_qdrant: bool = typer.Option(
        False, "--no-qdrant",
        help="Process to disk only. Skip the Qdrant upsert even if the "
             "server is reachable. Useful for offline runs."),
) -> None:
    """Dual-track ingest from data/inbox/.

    Narrative files (PDF, DOCX, MD, TXT) become markdown chunks under
    data/processed/narrative/ and get indexed into Qdrant.
    Numeric files (XLSX, CSV, JSON, XML) become Parquet files under
    data/processed/numeric/ with Markdown data cards (also indexed).
    PDF tables are extracted with pdfplumber + camelot cross-check:
    below the confidence floor they degrade to narrative pipe-tables.
    Gold tables in data/gold/ are checksum-verified and trusted at 1.0.
    Every attempt is logged to data/processed/audit.sqlite.
    """
    import os
    if no_qdrant:
        os.environ["INGEST_ENABLE_QDRANT"] = "0"
    from src.ingest.pipeline import IngestConfig, run
    cfg = IngestConfig.load()
    stats = run(cfg, force=force, log_fn=lambda m: typer.echo(m))
    typer.echo("")
    typer.echo(f"[ingest] scanned {stats.files_scanned}  "
               f"narrative-ok {stats.narrative_ok}  "
               f"numeric-ok {stats.numeric_ok}  "
               f"structured-ok {stats.structured_ok}  "
               f"gold {stats.gold_loaded}  "
               f"skipped {stats.skipped}  "
               f"degraded-tables {stats.tables_degraded_to_narrative}  "
               f"failures {stats.failures}  "
               f"qdrant-points {stats.qdrant_points}"
               + ("  [qdrant SKIPPED]" if stats.qdrant_skipped else ""))
    if stats.failures:
        raise typer.Exit(code=1)


@app.command("build-graph")
def build_graph() -> None:
    """Build Neo4j graph + Qdrant index from processed data. [Phase 4]"""
    _not_impl(4, "build-graph")


@app.command()
def query(question: str) -> None:
    """Ask the hybrid retrieval router a question. [Phase 5]"""
    _not_impl(5, "query")


@app.command("review-merges")
def review_merges() -> None:
    """Interactive CLI for the ER review queue. [Phase 4]"""
    from cli.review_merges import main
    main()


@app.command()
def unmerge(entity_id: str) -> None:
    """Reverse a prior merge. Merges are non-destructive. [Phase 4]"""
    from cli.unmerge import main
    main(entity_id)


if __name__ == "__main__":
    app()
