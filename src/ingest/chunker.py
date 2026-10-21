"""Narrative chunker.

Phase 3 keeps this simple: character-length windows with a soft break at
sentence boundaries and a configurable overlap. Deliberately NOT using a
tokenizer here — we don't want a model dependency this low in the stack
and bge-m3 is tolerant of coarse chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    char_start: int
    char_end: int
    index: int           # 0-based chunk index within the document


def chunk(text: str, *, target_chars: int = 1200,
          overlap_chars: int = 150) -> list[Chunk]:
    """Return a list of chunks covering ``text``.

    The window advances by (target - overlap) characters; within each
    window we trim to the last sentence boundary so chunks don't end
    mid-sentence. A document shorter than ``target_chars`` becomes a
    single chunk.
    """
    if not text.strip():
        return []
    n = len(text)
    if n <= target_chars:
        return [Chunk(text=text, char_start=0, char_end=n, index=0)]

    out: list[Chunk] = []
    step = max(1, target_chars - overlap_chars)
    i = 0
    idx = 0
    while i < n:
        end = min(n, i + target_chars)
        window = text[i:end]
        # Trim to the last sentence boundary within the window, except on
        # the final chunk where we take whatever remains.
        if end < n:
            match_end = 0
            for m in _SENT_BOUNDARY.finditer(window):
                match_end = m.end()
            if match_end > target_chars * 0.5:
                window = window[:match_end]
                end = i + match_end
        out.append(Chunk(text=window.strip(), char_start=i,
                         char_end=end, index=idx))
        idx += 1
        if end >= n:
            break
        i += step
    return out
