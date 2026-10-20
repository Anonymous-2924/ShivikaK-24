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
    typer.echo(f"[not implemented in Phase 1] {what} lands in Phase {phase}.", err=True)
    sys.exit(2)


@app.command()
def ingest() -> None:
    """Dual-track ingest from data/inbox/. [Phase 3]"""
    _not_impl(3, "ingest")


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
