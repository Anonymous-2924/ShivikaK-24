"""Top-level CLI. Phase 1: skeleton only.

Every subcommand is wired so Make targets end-to-end, but each prints a
clear 'not implemented in Phase <n>' and exits non-zero. This is deliberate:
we never want a Make target to appear to succeed when it did nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

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


@app.command()
def extract(
    narrative_dir: str = typer.Option(
        "data/processed/narrative",
        help="Directory of narrative markdown files (output of `ingest`)."),
    checkpoint: str = typer.Option(
        "data/processed/extractions.jsonl",
        help="Per-chunk extraction checkpoint — resumable across runs."),
    verify: bool = typer.Option(
        True, "--verify/--no-verify",
        help="Run the verifier model on high-impact edges + sampled chunks."),
    sample_rate: float = typer.Option(
        0.10, help="Verifier sampling rate for non-high-impact chunks."),
) -> None:
    """LLM-driven entity + relation extraction over the narrative track.

    Two separate passes per chunk (entities, then relations). Proposer
    is OLLAMA_EXTRACT_MODEL on OLLAMA_CLOUD_HOST; verifier is
    OLLAMA_VERIFY_MODEL. On a session-cap error the extractor
    checkpoints and exits 0 — rerun after the window resets.
    """
    import os

    from src.extract.client import OllamaChat
    from src.extract.extractor import ExtractionConfig
    from src.extract.extractor import run as run_extract

    host = os.environ.get("OLLAMA_CLOUD_HOST", "https://ollama.com")
    api_key = os.environ.get("OLLAMA_CLOUD_API_KEY") or None
    prop_model = os.environ.get("OLLAMA_EXTRACT_MODEL", "gpt-oss:20b")
    verif_model = os.environ.get("OLLAMA_VERIFY_MODEL", "nemotron-3-ultra")
    if not api_key:
        typer.echo("OLLAMA_CLOUD_API_KEY is not set in your environment.",
                   err=True)
        raise typer.Exit(code=2)

    proposer = OllamaChat(host=host, api_key=api_key, model=prop_model)
    verifier = (OllamaChat(host=host, api_key=api_key, model=verif_model)
                if verify else None)

    cfg = ExtractionConfig(
        narrative_dir=Path(narrative_dir),
        checkpoint_path=Path(checkpoint),
        proposer=proposer, verifier=verifier,
        verifier_sample_rate=sample_rate,
    )
    stats = run_extract(cfg, log_fn=lambda m: typer.echo(m))
    typer.echo(
        f"[extract] files={stats.files_scanned}  "
        f"chunks new={stats.chunks_done_new}  "
        f"skipped-done={stats.chunks_skipped_done}  "
        f"entities={stats.entities}  "
        f"relations kept={stats.relations_kept}  "
        f"verifier-calls={stats.verifier_calls}  "
        f"session-cap-hit={stats.session_cap_hit}  "
        f"failures={stats.failures}"
    )


@app.command()
def resolve(
    aliases: str = typer.Option(
        "config/aliases.yaml",
        help="Hand-curated alias overrides (YAML)."),
    auto_merge_threshold: float = typer.Option(0.92),
    review_threshold: float = typer.Option(0.78),
) -> None:
    """Run entity resolution across structured + extracted entities.

    Reads suppliers_export.json, plants_export.xml etc. from
    data/inbox/, plus any entities already captured by the extractor,
    scores every candidate pair within type-and-country blocks, and
    writes to data/processed/merges.sqlite. Auto-merges happen inline;
    review-band pairs go to the review queue — run `python -m cli
    review-merges` to clear them.
    """
    _not_impl_text = ("[resolve] Phase 4 integration bootstrap — populate "
                      "entities from your ingest run first, then this "
                      "becomes a one-shot. See src/resolve/resolver.py "
                      "for the API; its unit test covers the full flow.")
    typer.echo(_not_impl_text)
    _ = aliases, auto_merge_threshold, review_threshold


@app.command("build-graph")
def build_graph(
    structured_dir: str = typer.Option(
        "data/inbox",
        help="Directory holding the ERP JSON/XML exports."),
    extractions: str = typer.Option(
        "data/processed/extractions.jsonl"),
    numeric_dir: str = typer.Option("data/processed/numeric"),
) -> None:
    """Build Neo4j graph from structured exports + LLM extractions + data cards."""
    import os

    from src.graph.builder import (
        build_from_data_cards,
        build_from_extractions,
        build_from_structured,
    )
    from src.graph.writer import Neo4jWriter
    from src.resolve.merges import MergeStore

    writer = Neo4jWriter(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", ""),
    )
    writer.ensure_constraints()
    store = MergeStore(Path("data/processed/merges.sqlite"))

    s1 = build_from_structured(
        writer=writer, resolver=store,
        structured_json_dir=Path(structured_dir),
        log_fn=lambda m: typer.echo(m),
    )
    s2 = build_from_data_cards(
        writer=writer, resolver=store,
        numeric_dir=Path(numeric_dir),
        log_fn=lambda m: typer.echo(m),
    )
    # name_to_id is Phase 5 bootstrap — defer; extractions-only run reads
    # the structured suppliers export and maps canonical names → ids.
    name_to_id: dict[str, str] = {}
    s3 = build_from_extractions(
        writer=writer, resolver=store,
        extractions_path=Path(extractions),
        name_to_id=name_to_id,
        log_fn=lambda m: typer.echo(m),
    )
    writer.close()
    store.close()
    total_edges = s1.edges_written + s2.edges_written + s3.edges_written
    rejected = (s1.edges_rejected_schema + s2.edges_rejected_schema
                + s3.edges_rejected_schema)
    typer.echo(
        f"[build-graph] structured edges={s1.edges_written}  "
        f"data-card edges={s2.edges_written}  "
        f"extracted edges={s3.edges_written}  "
        f"total={total_edges}  schema-rejected={rejected}"
    )


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
