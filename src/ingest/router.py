"""File router: decide which track a file goes down, based on extension.

Content-sniffing on top of extension is a Phase 4+ concern (OCR'd images
of tables, mislabelled .txt that's really CSV, etc.). Phase 3 trusts the
extension — generator and real inboxes both carry sane names.
"""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class Track(StrEnum):
    NARRATIVE  = "narrative"
    NUMERIC    = "numeric"
    STRUCTURED = "structured"
    IMAGE      = "image"
    SKIP       = "skip"


_EXT_TO_TRACK: dict[str, Track] = {
    # Narrative
    ".pdf":  Track.NARRATIVE,   # pdfplumber prose + table-with-confidence
    ".docx": Track.NARRATIVE,
    ".md":   Track.NARRATIVE,
    ".txt":  Track.NARRATIVE,
    ".rtf":  Track.NARRATIVE,
    # Numeric
    ".xlsx": Track.NUMERIC,
    ".xls":  Track.NUMERIC,
    ".csv":  Track.NUMERIC,
    ".tsv":  Track.NUMERIC,
    # Structured (ERP-style exports: treated like numeric but with a flatten step)
    ".json": Track.STRUCTURED,
    ".xml":  Track.STRUCTURED,
    # Image (Phase 4: vision pass)
    ".png":  Track.IMAGE,
    ".jpg":  Track.IMAGE,
    ".jpeg": Track.IMAGE,
    # Explicit skip
    ".DS_Store": Track.SKIP,
}


def classify(path: Path) -> Track:
    """Return the track for a file. Unknown extensions skip (logged by caller)."""
    if path.name.startswith("."):
        return Track.SKIP
    if path.name == "README.md":
        # Inbox docs are instructions, not corpus material.
        return Track.SKIP
    return _EXT_TO_TRACK.get(path.suffix.lower(), Track.SKIP)
