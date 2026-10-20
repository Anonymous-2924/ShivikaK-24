"""Collector for all mess injected by the generator.

Writers call ``log.event(category, detail)`` as they corrupt things;
``log.write(path)`` at the end emits ``REALISM_LOG.md`` so the ingest
pipeline has an honest answer sheet for what it should have detected.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RealismLog:
    """Append-only log of deliberate mess."""
    events: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def event(self, category: str, detail: str) -> None:
        self.events[category].append(detail)
        self.counters[category] += 1

    def bump(self, category: str, n: int = 1) -> None:
        """For high-volume cases where listing every instance is noise."""
        self.counters[category] += n

    def write(self, path: Path) -> None:
        lines: list[str] = []
        lines.append("# Deliberate Realism Mess — Generator Audit Log")
        lines.append("")
        lines.append(
            "This file lists mess the generator INTENTIONALLY injected. "
            "It is the answer sheet: a working ingest pipeline should "
            "detect many of these and surface them as low-confidence "
            "edges, review-queue candidates, or validator warnings. The "
            "generator is deterministic given its `--seed`, so counts "
            "below reproduce exactly on a rerun."
        )
        lines.append("")
        lines.append("## Summary (counters)")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("|---|---:|")
        for cat in sorted(self.counters):
            lines.append(f"| {cat} | {self.counters[cat]} |")
        lines.append("")
        lines.append("## Detail (first 30 of each)")
        lines.append("")
        for cat in sorted(self.events):
            lines.append(f"### {cat}")
            lines.append("")
            for d in self.events[cat][:30]:
                lines.append(f"- {d}")
            if len(self.events[cat]) > 30:
                lines.append(f"- ... and {len(self.events[cat]) - 30} more")
            lines.append("")
        path.write_text("\n".join(lines))
