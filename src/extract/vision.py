"""Per-image vision extractor.

Reads one image file, sends to the vision model, validates the response,
and renders a 'chart card' Markdown document ready to drop into the
narrative track.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.extract import prompts
from src.extract.client import OllamaChat
from src.extract.validators import validate_vision


@dataclass
class VisionResult:
    confidence: float            # already capped
    self_reported_confidence: float
    markdown: str
    model: str
    raw: dict                    # normalised payload for the audit log


def extract_image(path: Path, *, vision_client: OllamaChat,
                   confidence_cap: float = 0.65) -> VisionResult:
    image_bytes = path.read_bytes()
    resp = vision_client.chat_vision_json(
        system=prompts.VISION_SYSTEM,
        user=prompts.vision_user(source_file=path.name),
        image_bytes=image_bytes,
    )
    r = validate_vision(resp.parsed, confidence_cap=confidence_cap)
    payload = r.entities[0] if r.entities else {
        "chart_type": "other", "title": "", "description": "",
        "data_points": [], "entities_mentioned": [],
        "x_axis_label": "", "y_axis_label": "", "x_tick_labels": [],
        "notes": "vision payload did not parse",
        "confidence": 0.0, "self_reported_confidence": 0.0,
    }
    md = _render_chart_card(path, payload, model=resp.model)
    return VisionResult(
        confidence=float(payload["confidence"]),
        self_reported_confidence=float(payload["self_reported_confidence"]),
        markdown=md,
        model=resp.model,
        raw=payload,
    )


def _render_chart_card(path: Path, p: dict[str, Any], *, model: str) -> str:
    lines: list[str] = []
    lines.append(f"# Chart: {path.stem}")
    lines.append("")
    lines.append(f"- **Source file:** `{path.name}`")
    lines.append("- **Extraction method:** vision")
    lines.append(f"- **Model:** {model}")
    lines.append(f"- **Confidence (capped):** {p['confidence']:.2f}")
    lines.append(f"- **Self-reported confidence:** {p['self_reported_confidence']:.2f}")
    lines.append(f"- **Chart type:** {p['chart_type']}")
    if p.get("title"):
        lines.append(f"- **Title:** {p['title']}")
    if p.get("x_axis_label"):
        lines.append(f"- **X axis:** {p['x_axis_label']}")
    if p.get("y_axis_label"):
        lines.append(f"- **Y axis:** {p['y_axis_label']}")
    if p.get("notes"):
        lines.append(f"- **Caveat:** {p['notes']}")
    lines.append("")
    lines.append("## Description")
    lines.append("")
    lines.append(p.get("description") or "_(no description produced)_")
    lines.append("")
    if p.get("entities_mentioned"):
        lines.append("## Entities mentioned")
        lines.append("")
        for e in p["entities_mentioned"]:
            lines.append(f"- {e}")
        lines.append("")
    data_points = p.get("data_points") or []
    if data_points:
        lines.append("## Data points (as read)")
        lines.append("")
        lines.append("| Series | X | Y |")
        lines.append("|---|---|---:|")
        for dp in data_points[:50]:
            series = str(dp.get("series", "")).replace("|", "\\|")
            x = str(dp.get("x", "")).replace("|", "\\|")
            y = dp.get("y", "")
            lines.append(f"| {series} | {x} | {y} |")
        if len(data_points) > 50:
            lines.append(f"| ... | ... | (+{len(data_points) - 50} more) |")
        lines.append("")
    return "\n".join(lines)
