"""Per-chunk extraction state so re-runs resume cleanly.

File: data/processed/extractions.jsonl — one JSON line per completed
(source_file, chunk_index). Open-ended append-only; corrupted lines are
skipped on read.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractionRecord:
    source_file: str
    chunk_index: int
    entities: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    note: str | None = None

    def to_json_line(self) -> str:
        return json.dumps({
            "source_file": self.source_file,
            "chunk_index": self.chunk_index,
            "entities": self.entities,
            "relations": self.relations,
            "note": self.note,
        }, ensure_ascii=False)


class Checkpoint:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        self._done: set[tuple[str, int]] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
                self._done.add((obj["source_file"], int(obj["chunk_index"])))
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue

    def already_done(self, source_file: str, chunk_index: int) -> bool:
        return (source_file, chunk_index) in self._done

    def mark_done(self, record: ExtractionRecord) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(record.to_json_line() + "\n")
        self._done.add((record.source_file, record.chunk_index))

    def all_records(self) -> list[dict]:
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def count(self) -> int:
        return len(self._done)
