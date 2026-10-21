"""End-to-end LLM extraction pipeline.

Walks the processed narrative markdown, re-chunks each file, and for
every chunk:
  1. Calls the PROPOSER for entities (constrained JSON).
  2. Validates and keeps only verbatim-present entities.
  3. Calls the PROPOSER for relations against the kept entity set.
  4. Validates and keeps only well-formed, vocabulary-conformant relations.
  5. Decides whether to verify (high-impact edge type OR verifier sampling
     rate hit): if so, calls the VERIFIER and folds the verdict in.
  6. Records to ``extractions.jsonl`` and advances.

On ``SessionCapReached`` from the client we checkpoint cleanly, log, and
exit with code 0 — rerunning picks up from the next chunk.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from src.extract import prompts
from src.extract.checkpoint import Checkpoint, ExtractionRecord
from src.extract.client import OllamaChat, SessionCapReached
from src.extract.validators import apply_verifier, validate_entities, validate_relations
from src.ingest.chunker import chunk as chunk_text


@dataclass
class ExtractionConfig:
    narrative_dir: Path
    checkpoint_path: Path
    proposer: OllamaChat
    verifier: OllamaChat | None
    verifier_sample_rate: float = 0.10
    high_impact_edge_types: tuple[str, ...] = (
        "supplied_by", "manufactured_at", "disrupted_by",
    )
    chunk_target_chars: int = 1200
    chunk_overlap_chars: int = 150
    rng_seed: int = 42


@dataclass
class ExtractionStats:
    files_scanned: int = 0
    chunks_scanned: int = 0
    chunks_done_new: int = 0
    chunks_skipped_done: int = 0
    entities: int = 0
    relations_proposer: int = 0
    relations_dropped_validator: int = 0
    relations_rejected_verifier: int = 0
    relations_kept: int = 0
    verifier_calls: int = 0
    session_cap_hit: bool = False
    failures: int = 0


def run(cfg: ExtractionConfig, *, log_fn=print) -> ExtractionStats:
    stats = ExtractionStats()
    ckpt = Checkpoint(cfg.checkpoint_path)
    rng = random.Random(cfg.rng_seed)
    files = sorted(cfg.narrative_dir.glob("*.md"))
    stats.files_scanned = len(files)
    log_fn(f"[extract] narrative files: {len(files)}  "
           f"already-done chunks: {ckpt.count()}")

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
            chunks = chunk_text(text, target_chars=cfg.chunk_target_chars,
                                 overlap_chars=cfg.chunk_overlap_chars)
            for c in chunks:
                stats.chunks_scanned += 1
                if ckpt.already_done(path.name, c.index):
                    stats.chunks_skipped_done += 1
                    continue
                try:
                    _extract_chunk(path, c, cfg, ckpt, stats, rng)
                except SessionCapReached as exc:
                    stats.session_cap_hit = True
                    log_fn(f"[extract] session cap reached: {exc}. "
                           f"Checkpointed {ckpt.count()} chunks. "
                           f"Rerun after the window resets.")
                    return stats
        except Exception as exc:   # noqa: BLE001
            stats.failures += 1
            log_fn(f"[extract] FAILED on {path.name}: "
                   f"{type(exc).__name__}: {exc}")
    log_fn(f"[extract] done. chunks new={stats.chunks_done_new}  "
           f"skipped-done={stats.chunks_skipped_done}  "
           f"relations kept={stats.relations_kept}  "
           f"verifier calls={stats.verifier_calls}  "
           f"failures={stats.failures}")
    return stats


def _extract_chunk(path: Path, chunk, cfg: ExtractionConfig,
                   ckpt: Checkpoint, stats: ExtractionStats,
                   rng: random.Random) -> None:
    # Pass 1: entities.
    e_res = cfg.proposer.chat_json(
        system=prompts.ENTITY_SYSTEM,
        user=prompts.entity_user(chunk.text,
                                   source_file=path.name,
                                   chunk_index=chunk.index),
    )
    e_valid = validate_entities(e_res.parsed, chunk_text=chunk.text)
    stats.entities += len(e_valid.entities)

    entity_names = {e["name"] for e in e_valid.entities}
    if not entity_names:
        # No entities → no relations possible. Record and move on.
        ckpt.mark_done(ExtractionRecord(
            source_file=path.name, chunk_index=chunk.index,
            entities=[], relations=[], note="no entities",
        ))
        stats.chunks_done_new += 1
        return

    # Pass 2: relations.
    r_res = cfg.proposer.chat_json(
        system=prompts.RELATION_SYSTEM,
        user=prompts.relation_user(chunk.text, e_valid.entities,
                                     source_file=path.name,
                                     chunk_index=chunk.index),
    )
    r_valid = validate_relations(r_res.parsed, entity_names=entity_names,
                                  chunk_text=chunk.text)
    stats.relations_proposer += len(r_valid.relations)
    stats.relations_dropped_validator += r_valid.dropped
    kept = r_valid.relations

    # Decide whether to verify.
    if kept and cfg.verifier is not None:
        if _should_verify(kept, cfg, rng):
            stats.verifier_calls += 1
            v_res = cfg.verifier.chat_json(
                system=prompts.VERIFIER_SYSTEM,
                user=prompts.verifier_user(chunk.text, kept,
                                             source_file=path.name,
                                             chunk_index=chunk.index),
            )
            before = len(kept)
            kept = apply_verifier(v_res.parsed, kept)
            stats.relations_rejected_verifier += (before - len(kept))

    stats.relations_kept += len(kept)
    ckpt.mark_done(ExtractionRecord(
        source_file=path.name, chunk_index=chunk.index,
        entities=e_valid.entities, relations=kept,
    ))
    stats.chunks_done_new += 1


def _should_verify(relations: list[dict], cfg: ExtractionConfig,
                    rng: random.Random) -> bool:
    """Always verify high-impact edges. Otherwise sample at the configured
    rate (per-chunk, so one draw covers all its relations)."""
    if any(r["type"] in cfg.high_impact_edge_types for r in relations):
        return True
    return rng.random() < cfg.verifier_sample_rate
