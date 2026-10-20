"""Ingest orchestrator.

Walks ``data/inbox/``, routes each file by extension, writes narrative
markdown to ``data/processed/narrative/`` and parquet + data cards to
``data/processed/numeric/``, and indexes narrative chunks + data cards to
Qdrant if the index is reachable. Every attempt is logged to the SQLite
audit log; rerunning the ingest is idempotent and skips files that
already succeeded for the same content hash.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.ingest import gold, narrative, numeric, structured, tables
from src.ingest.audit import AuditLog
from src.ingest.chunker import chunk as chunk_text
from src.ingest.data_card import write_data_card
from src.ingest.router import Track, classify


@dataclass
class IngestConfig:
    inbox: Path
    gold: Path
    processed_narrative: Path
    processed_numeric: Path
    audit_path: Path
    table_confidence_floor: float
    enable_qdrant: bool
    qdrant_url: str
    qdrant_api_key: str | None
    ollama_embed_host: str
    ollama_embed_model: str
    ollama_embed_dim: int

    @classmethod
    def load(cls, settings_path: Path = Path("config/settings.yaml")) -> IngestConfig:
        s = yaml.safe_load(settings_path.read_text())
        p = s["paths"]
        return cls(
            inbox=Path(p["inbox"]),
            gold=Path(p["gold"]),
            processed_narrative=Path(p["processed_narrative"]),
            processed_numeric=Path(p["processed_numeric"]),
            audit_path=Path(p["processed_narrative"]).parent / "audit.sqlite",
            table_confidence_floor=float(
                s["ingest"].get("table_confidence_floor", 0.75)
            ),
            enable_qdrant=os.environ.get("INGEST_ENABLE_QDRANT", "1") != "0",
            qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.environ.get("QDRANT_API_KEY") or None,
            ollama_embed_host=os.environ.get("OLLAMA_EMBED_HOST",
                                              "http://localhost:11434"),
            ollama_embed_model=os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3"),
            ollama_embed_dim=int(os.environ.get("OLLAMA_EMBED_DIM", "1024")),
        )


@dataclass
class IngestStats:
    files_scanned: int = 0
    narrative_ok: int = 0
    numeric_ok: int = 0
    structured_ok: int = 0
    gold_loaded: int = 0
    skipped: int = 0
    failures: int = 0
    tables_degraded_to_narrative: int = 0
    qdrant_points: int = 0
    qdrant_skipped: bool = False


def run(cfg: IngestConfig, *, force: bool = False,
        log_fn=print) -> IngestStats:
    stats = IngestStats()
    cfg.processed_narrative.mkdir(parents=True, exist_ok=True)
    cfg.processed_numeric.mkdir(parents=True, exist_ok=True)

    audit = AuditLog(cfg.audit_path)

    # 1. Load gold tables first — they take precedence over anything in the
    # inbox and feed the data-card index at confidence 1.0.
    gold_tables = gold.scan(cfg.gold)
    log_fn(f"[ingest] gold tables: {len(gold_tables)}")

    # 2. Walk the inbox.
    inbox_files = _list_inbox(cfg.inbox)
    stats.files_scanned = len(inbox_files)
    log_fn(f"[ingest] inbox files: {len(inbox_files)}")

    # 3. Lazy init indexer. If Qdrant/Ollama aren't reachable we still
    # process to disk and record a warning in the stats.
    indexer, embedder = _init_index(cfg, log_fn)
    if indexer is None:
        stats.qdrant_skipped = True

    pending_index: list = []     # list of (IndexDoc, text) to batch-embed

    for path in inbox_files:
        try:
            track = classify(path)
            sha = _sha256(path)
            if not force and audit.already_succeeded(str(path), sha):
                stats.skipped += 1
                continue
            if track == Track.SKIP:
                with audit.record(file=str(path), sha256=sha,
                                   track="skipped",
                                   extractor="router") as rec:
                    rec.done(confidence=1.0, note="skipped by router")
                stats.skipped += 1
                continue
            if track == Track.IMAGE:
                with audit.record(file=str(path), sha256=sha,
                                   track="image", extractor="router") as rec:
                    rec.done(confidence=0.0, note="image track lands in Phase 4")
                stats.skipped += 1
                continue
            if track == Track.NARRATIVE:
                _handle_narrative(path, sha, cfg, audit, stats,
                                   pending_index, log_fn)
            elif track == Track.NUMERIC:
                _handle_numeric(path, sha, cfg, audit, stats,
                                 pending_index, log_fn)
            elif track == Track.STRUCTURED:
                _handle_structured(path, sha, cfg, audit, stats,
                                    pending_index, log_fn)
        except Exception as exc:   # noqa: BLE001
            stats.failures += 1
            log_fn(f"[ingest] FAILED {path.name}: {type(exc).__name__}: {exc}")

    # 4. Gold tables → processed/numeric + data cards.
    for gt in gold_tables:
        try:
            dest = gold.install(gt, cfg.processed_numeric)
            card_path = dest.with_suffix(".md")
            # Build a NumericTable stub so write_data_card can describe it.
            card_table = _numeric_from_gold(gt)
            with audit.record(file=str(gt.parquet_src),
                               sha256=_sha256(gt.parquet_src),
                               track="gold", extractor="gold") as rec:
                write_data_card(
                    out_path=card_path, parquet_path=dest,
                    source_file=gt.parquet_src, table=card_table,
                    row_count=gt.rows,
                    extraction_method="manual", confidence=1.0,
                    period=gt.schema.get("period", {}).get("valid_from"),
                    linked_entities=[gt.schema["linked_entity"]]
                                     if gt.schema.get("linked_entity") else None,
                )
                rec.done(confidence=1.0, rows_or_chars=gt.rows,
                         note="gold table loaded")
            stats.gold_loaded += 1
            if indexer:
                pending_index.append(_data_card_indexdoc(
                    source_file=gt.parquet_src, parquet=dest,
                    card_text=card_path.read_text(),
                    confidence=1.0, extraction_method="manual",
                ))
        except Exception as exc:   # noqa: BLE001
            stats.failures += 1
            log_fn(f"[ingest] gold install FAILED {gt.basename}: {exc}")

    # 5. Flush pending index items in reasonable batches.
    if indexer and embedder and pending_index:
        log_fn(f"[ingest] embedding+upserting {len(pending_index)} points")
        _upsert_batched(indexer, embedder, pending_index, log_fn)
        stats.qdrant_points = len(pending_index)

    audit.close()
    return stats


# ---------- track handlers ----------
def _handle_narrative(path: Path, sha: str, cfg: IngestConfig,
                      audit: AuditLog, stats: IngestStats,
                      pending_index: list, log_fn) -> None:
    ext = path.suffix.lower()
    parsed = _parse_narrative(path, ext)
    md = parsed.markdown
    # PDF-only: also run the two-extractor table pass and append any
    # extracted tables inline as pipe-tables (narrative), while also
    # routing high-confidence ones to parquet (numeric).
    if ext == ".pdf":
        md = _augment_pdf_with_tables(path, md, sha, cfg, audit,
                                       stats, pending_index, log_fn)
    # Persist narrative markdown.
    out_md = cfg.processed_narrative / f"{path.stem}.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md)
    # Chunk and queue for indexing.
    chunks = chunk_text(md)
    with audit.record(file=str(path), sha256=sha,
                      track="narrative", extractor=parsed.extractor) as rec:
        rec.done(confidence=parsed.confidence, rows_or_chars=len(md),
                 note=parsed.note)
    for c in chunks:
        pending_index.append(_chunk_indexdoc(
            source_file=path, chunk=c,
            confidence=parsed.confidence, extraction_method="structured",
        ))
    stats.narrative_ok += 1


def _augment_pdf_with_tables(path: Path, prose_md: str, sha: str,
                              cfg: IngestConfig, audit: AuditLog,
                              stats: IngestStats, pending_index: list,
                              log_fn) -> str:
    extracted, note = tables.extract_tables(str(path))
    if not extracted:
        return prose_md
    appended: list[str] = []
    for i, t in enumerate(extracted):
        with audit.record(file=str(path), sha256=sha,
                          track="numeric" if t.confidence >= cfg.table_confidence_floor
                                else "narrative",
                          extractor=f"table:{t.extractor}") as rec:
            if t.confidence >= cfg.table_confidence_floor:
                # Promote to parquet.
                nt = _table_to_numeric(path, i, t)
                parquet = cfg.processed_numeric / f"{path.stem}_tbl{i:02d}_p{t.page}.parquet"
                rows = nt.write_parquet(parquet)
                card_path = parquet.with_suffix(".md")
                write_data_card(
                    out_path=card_path, parquet_path=parquet,
                    source_file=path, table=nt, row_count=rows,
                    extraction_method="structured",
                    confidence=t.confidence,
                )
                rec.done(confidence=t.confidence, rows_or_chars=rows,
                         note=note or f"table page {t.page}")
                pending_index.append(_data_card_indexdoc(
                    source_file=path, parquet=parquet,
                    card_text=card_path.read_text(),
                    confidence=t.confidence,
                    extraction_method="structured",
                ))
                stats.numeric_ok += 1
            else:
                # Degrade: embed as narrative pipe-table.
                stats.tables_degraded_to_narrative += 1
                rec.done(confidence=t.confidence,
                         note=f"below floor ({cfg.table_confidence_floor:.2f}); "
                              f"degraded to narrative")
                appended.append(
                    f"\n\n### Table on page {t.page} (low-confidence, {t.confidence:.2f})\n\n"
                    + tables.rows_to_pipe_table(t.rows)
                )
    if appended:
        return prose_md + "\n\n" + "\n\n".join(appended)
    return prose_md


def _handle_numeric(path: Path, sha: str, cfg: IngestConfig,
                     audit: AuditLog, stats: IngestStats,
                     pending_index: list, log_fn) -> None:
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        tables_list = numeric.parse_excel(path)
    else:
        tables_list = numeric.parse_csv(path)
    for nt in tables_list:
        safe_sheet = _safe_sheet(nt.sheet_or_name)
        parquet = cfg.processed_numeric / f"{path.stem}__{safe_sheet}.parquet"
        with audit.record(file=str(path), sha256=sha,
                          track="numeric", extractor=nt.extractor) as rec:
            if nt.confidence < cfg.table_confidence_floor and nt.rows:
                # Below floor on a structured table: this is unusual for
                # Excel/CSV (shape is clean), but if it happens, degrade
                # to a narrative pipe-table rather than lie about parquet.
                stats.tables_degraded_to_narrative += 1
                rec.done(confidence=nt.confidence,
                         note="below floor; degraded to narrative")
                degraded_md = (
                    f"# {path.stem} / {nt.sheet_or_name}\n\n"
                    + tables.rows_to_pipe_table(
                        [nt.columns] + [[str(c) for c in r] for r in nt.rows[:200]])
                )
                out_md = cfg.processed_narrative / f"{path.stem}__{safe_sheet}.md"
                out_md.write_text(degraded_md)
                for c in chunk_text(degraded_md):
                    pending_index.append(_chunk_indexdoc(
                        source_file=path, chunk=c,
                        confidence=nt.confidence,
                        extraction_method="structured",
                    ))
                continue
            rows = nt.write_parquet(parquet)
            card_path = parquet.with_suffix(".md")
            write_data_card(
                out_path=card_path, parquet_path=parquet,
                source_file=path, table=nt, row_count=rows,
                extraction_method="structured", confidence=nt.confidence,
            )
            rec.done(confidence=nt.confidence, rows_or_chars=rows,
                     note=nt.note)
            pending_index.append(_data_card_indexdoc(
                source_file=path, parquet=parquet,
                card_text=card_path.read_text(),
                confidence=nt.confidence,
                extraction_method="structured",
            ))
            stats.numeric_ok += 1


def _handle_structured(path: Path, sha: str, cfg: IngestConfig,
                        audit: AuditLog, stats: IngestStats,
                        pending_index: list, log_fn) -> None:
    ext = path.suffix.lower()
    tables_list = (structured.parse_json(path) if ext == ".json"
                    else structured.parse_xml(path))
    for nt in tables_list:
        safe_sheet = _safe_sheet(nt.sheet_or_name)
        parquet = cfg.processed_numeric / f"{path.stem}__{safe_sheet}.parquet"
        with audit.record(file=str(path), sha256=sha,
                          track="structured", extractor=nt.extractor) as rec:
            rows = nt.write_parquet(parquet)
            card_path = parquet.with_suffix(".md")
            write_data_card(
                out_path=card_path, parquet_path=parquet,
                source_file=path, table=nt, row_count=rows,
                extraction_method="structured", confidence=nt.confidence,
            )
            rec.done(confidence=nt.confidence, rows_or_chars=rows,
                     note=nt.note)
            pending_index.append(_data_card_indexdoc(
                source_file=path, parquet=parquet,
                card_text=card_path.read_text(),
                confidence=nt.confidence,
                extraction_method="structured",
            ))
            stats.structured_ok += 1


# ---------- helpers ----------
def _parse_narrative(path: Path, ext: str):
    if ext == ".docx":
        return narrative.parse_docx(path)
    if ext == ".pdf":
        return narrative.parse_pdf_prose(path)
    return narrative.parse_plaintext(path)


def _init_index(cfg: IngestConfig, log_fn):
    if not cfg.enable_qdrant:
        log_fn("[ingest] Qdrant disabled by INGEST_ENABLE_QDRANT=0")
        return None, None
    try:
        from src.index.embeddings import Embedder
        from src.index.qdrant import QdrantIndex
        emb = Embedder(host=cfg.ollama_embed_host,
                        model=cfg.ollama_embed_model,
                        expected_dim=cfg.ollama_embed_dim)
        dim = emb.ping()
        idx = QdrantIndex(url=cfg.qdrant_url, vector_dim=dim,
                           api_key=cfg.qdrant_api_key)
        idx.ensure_collection()
        return idx, emb
    except Exception as exc:   # noqa: BLE001
        log_fn(f"[ingest] Qdrant/Ollama unavailable: "
               f"{type(exc).__name__}: {exc}. "
               f"Continuing without indexing — ingest to disk still runs.")
        return None, None


def _upsert_batched(indexer, embedder, pending: list, log_fn,
                    *, batch: int = 32) -> None:
    for i in range(0, len(pending), batch):
        slice_ = pending[i: i + batch]
        texts = [d.text for d in slice_]
        vecs = embedder.embed_many(texts)
        indexer.upsert(slice_, vecs)
        log_fn(f"[ingest]   indexed {min(i + batch, len(pending))}/{len(pending)}")


def _chunk_indexdoc(*, source_file: Path, chunk, confidence: float,
                    extraction_method: str):
    from src.index.qdrant import IndexDoc
    return IndexDoc(
        doc_id=f"{source_file.name}::chunk::{chunk.index}",
        text=chunk.text, kind="chunk",
        source_file=source_file.name, chunk_index=chunk.index,
        confidence=confidence, extraction_method=extraction_method,
        extra_payload={"char_start": chunk.char_start,
                       "char_end": chunk.char_end},
    )


def _data_card_indexdoc(*, source_file: Path, parquet: Path,
                        card_text: str, confidence: float,
                        extraction_method: str):
    from src.index.qdrant import IndexDoc
    return IndexDoc(
        doc_id=f"{source_file.name}::card::{parquet.stem}",
        text=card_text, kind="data_card",
        source_file=source_file.name, chunk_index=None,
        confidence=confidence, extraction_method=extraction_method,
        extra_payload={"parquet_path": str(parquet)},
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 64), b""):
            h.update(chunk)
    return h.hexdigest()


def _list_inbox(inbox: Path) -> list[Path]:
    if not inbox.exists():
        return []
    out: list[Path] = []
    for p in sorted(inbox.rglob("*")):
        if p.is_file():
            out.append(p)
    return out


def _safe_sheet(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_"
                    for c in name).strip("_") or "sheet"


def _numeric_from_gold(gt):
    from src.ingest.numeric import NumericTable
    return NumericTable(
        sheet_or_name=gt.basename,
        columns=[c["name"] for c in gt.schema.get("columns", [])],
        rows=[],
        confidence=1.0, extractor="gold",
        note="hand-verified; see gold schema.json for provenance",
    )


def _table_to_numeric(path: Path, i: int, t):
    from src.ingest.numeric import NumericTable
    header = t.rows[0]
    body = t.rows[1:]
    return NumericTable(
        sheet_or_name=f"table_p{t.page}_{i}",
        columns=[h or f"col_{j}" for j, h in enumerate(header)],
        rows=body,
        confidence=t.confidence,
        extractor=t.extractor,
    )
