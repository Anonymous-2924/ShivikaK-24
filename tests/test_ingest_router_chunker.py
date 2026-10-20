"""Unit tests for the two smallest ingest components."""
from __future__ import annotations

from pathlib import Path

from src.ingest.chunker import chunk
from src.ingest.router import Track, classify


# ---------- router ----------
def test_router_classifies_by_extension() -> None:
    assert classify(Path("foo.pdf")) is Track.NARRATIVE
    assert classify(Path("foo.docx")) is Track.NARRATIVE
    assert classify(Path("foo.md")) is Track.NARRATIVE
    assert classify(Path("foo.txt")) is Track.NARRATIVE
    assert classify(Path("foo.xlsx")) is Track.NUMERIC
    assert classify(Path("foo.CSV")) is Track.NUMERIC
    assert classify(Path("foo.json")) is Track.STRUCTURED
    assert classify(Path("foo.xml")) is Track.STRUCTURED
    assert classify(Path("foo.PNG")) is Track.IMAGE


def test_router_skips_inbox_readme_and_dotfiles() -> None:
    assert classify(Path("README.md")) is Track.SKIP
    assert classify(Path(".ignore")) is Track.SKIP
    assert classify(Path("something.unknown")) is Track.SKIP


# ---------- chunker ----------
def test_chunker_short_text_returns_single_chunk() -> None:
    text = "This is one short paragraph."
    out = chunk(text, target_chars=1000, overlap_chars=50)
    assert len(out) == 1
    assert out[0].text == text
    assert out[0].char_start == 0
    assert out[0].char_end == len(text)
    assert out[0].index == 0


def test_chunker_splits_long_text_with_overlap() -> None:
    sentences = [f"Sentence number {i} ends here." for i in range(1, 60)]
    text = " ".join(sentences)
    out = chunk(text, target_chars=400, overlap_chars=50)
    assert len(out) >= 3
    # Monotonic indices.
    assert [c.index for c in out] == list(range(len(out)))
    # Each chunk ends on a sentence boundary (period/space) except the last.
    for c in out[:-1]:
        assert c.text.rstrip().endswith(".")
    # Full coverage: last chunk reaches the end.
    assert out[-1].char_end == len(text)


def test_chunker_empty_text_is_no_chunks() -> None:
    assert chunk("") == []
    assert chunk("   \n\t ") == []
