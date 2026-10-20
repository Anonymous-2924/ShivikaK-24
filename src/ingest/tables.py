"""PDF table extraction with the two-extractor confidence check.

Primary: pdfplumber. Secondary (independent): camelot. If both find a
table at a comparable position, we compute the overlap of their cell
contents (Jaccard over normalised cell strings). The confidence we assign
to the extracted table is that overlap, capped by a bias term.

A table that scores below the configured floor is NOT written to Parquet
— it degrades to a narrative-track block of pipe-table markdown, which
the LLM extraction stage sees as unstructured text. The brief calls this
rule non-negotiable: the main defence against bad table parsing.

camelot has heavy system deps (ghostscript, opencv). If import fails we
run with pdfplumber only, cap confidence at a lower ceiling, and record
``note="camelot unavailable"`` in the audit log.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedTable:
    page: int
    rows: list[list[str]]       # rows[0] is header
    confidence: float
    extractor: str              # "pdfplumber" | "camelot" | "pdfplumber+camelot"


CAMELOT_UNAVAILABLE_CEIL = 0.80
JACCARD_MIN_FOR_AGREEMENT = 0.70


def extract_tables(pdf_path: str) -> tuple[list[ExtractedTable], str | None]:
    """Return (tables, note). ``note`` is populated when a degraded path
    was taken so the audit log can record why."""
    primary = _try_pdfplumber(pdf_path)
    try:
        secondary = _try_camelot(pdf_path)
    except Exception as exc:   # noqa: BLE001
        secondary = None
        camelot_err = f"camelot unavailable: {type(exc).__name__}"
    else:
        camelot_err = None

    if secondary is None:
        # pdfplumber-only path. Cap confidence; we have no cross-check.
        out = [
            ExtractedTable(page=t.page, rows=t.rows,
                           confidence=min(t.confidence, CAMELOT_UNAVAILABLE_CEIL),
                           extractor="pdfplumber")
            for t in primary
        ]
        return out, camelot_err

    # Have both. Pair tables by (page, row_count similarity), compute Jaccard.
    out: list[ExtractedTable] = []
    secondary_by_page: dict[int, list[_RawTable]] = {}
    for s in secondary:
        secondary_by_page.setdefault(s.page, []).append(s)

    for p in primary:
        best, best_j = None, 0.0
        for s in secondary_by_page.get(p.page, []):
            j = _cell_jaccard(p.rows, s.rows)
            if j > best_j:
                best, best_j = s, j
        if best is not None and best_j >= JACCARD_MIN_FOR_AGREEMENT:
            out.append(ExtractedTable(
                page=p.page, rows=p.rows, confidence=best_j,
                extractor="pdfplumber+camelot",
            ))
        else:
            # Disagreement or no partner. Confidence drops to the lower
            # of (pdfplumber's own confidence, the observed overlap).
            conf = min(p.confidence, max(best_j, 0.4))
            out.append(ExtractedTable(
                page=p.page, rows=p.rows, confidence=conf,
                extractor="pdfplumber",
            ))
    return out, None


# ---------- internals ----------
@dataclass(frozen=True)
class _RawTable:
    page: int
    rows: list[list[str]]
    confidence: float


def _try_pdfplumber(pdf_path: str) -> list[_RawTable]:
    import pdfplumber
    out: list[_RawTable] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            for raw in page.extract_tables() or []:
                rows = [[("" if c is None else str(c)).strip() for c in r] for r in raw]
                rows = [r for r in rows if any(c for c in r)]
                if not rows:
                    continue
                out.append(_RawTable(page=i, rows=rows,
                                      confidence=_shape_confidence(rows)))
    return out


def _try_camelot(pdf_path: str) -> list[_RawTable]:
    import camelot
    tables = camelot.read_pdf(pdf_path, pages="all", suppress_stdout=True)
    out: list[_RawTable] = []
    for t in tables:
        rows = [[("" if c is None else str(c)).strip() for c in row]
                for row in t.df.values.tolist()]
        rows = [r for r in rows if any(c for c in r)]
        if not rows:
            continue
        out.append(_RawTable(page=int(t.page), rows=rows,
                              confidence=float(getattr(t, "accuracy", 80) / 100.0)))
    return out


def _shape_confidence(rows: list[list[str]]) -> float:
    """Give a rough confidence from table shape alone, used only when the
    secondary extractor is unavailable to vote.

    Punishes jagged rows and empty columns; rewards consistent width and
    nontrivial size.
    """
    if not rows:
        return 0.0
    widths = {len(r) for r in rows}
    if len(widths) > 1:
        return 0.5
    n_cols = next(iter(widths))
    if n_cols < 2 or len(rows) < 2:
        return 0.55
    # Empty-cell fraction
    total = n_cols * len(rows)
    empty = sum(1 for r in rows for c in r if not c)
    density = 1.0 - (empty / total)
    return 0.6 + 0.3 * density    # 0.6..0.9 range


def _cell_jaccard(a: list[list[str]], b: list[list[str]]) -> float:
    """Compare cell-content sets, normalised to lowercase+stripped."""
    def norm(rows: list[list[str]]) -> set[str]:
        return {c.strip().lower() for r in rows for c in r if c.strip()}
    sa, sb = norm(a), norm(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def rows_to_pipe_table(rows: list[list[str]]) -> str:
    """Render a table as a Markdown pipe-table (narrative-track fallback)."""
    if not rows:
        return ""
    header = rows[0]
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join([" --- "] * len(header)) + "|"]
    for r in rows[1:]:
        padded = r + [""] * max(0, len(header) - len(r))
        out.append("| " + " | ".join(padded[:len(header)]) + " |")
    return "\n".join(out)
