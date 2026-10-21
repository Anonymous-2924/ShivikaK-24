"""Vision validator + chart-card renderer + pipeline wiring."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.extract.validators import validate_vision

_FULL = {
    "chart_type": "bar",
    "title": "Top suppliers by capacity",
    "x_axis_label": "Supplier",
    "y_axis_label": "Units/year",
    "x_tick_labels": ["Horizon", "Nile", "Cedar"],
    "data_points": [
        {"series": "capacity", "x": "Horizon", "y": 1_000_000},
        {"series": "capacity", "x": "Nile",     "y": 820_000},
        {"series": "capacity", "x": "Cedar",    "y": "not a number"},
    ],
    "entities_mentioned": ["Horizon Textiles", "Nile Spinning",
                            "Cedar Enterprises"],
    "description": "Bar chart showing capacity ranks across three suppliers.",
    "confidence": 0.92,   # self-reported — should be capped
    "notes": "y-axis labels slightly cropped",
}


def test_validate_vision_caps_confidence_and_drops_nonnumeric() -> None:
    r = validate_vision(_FULL, confidence_cap=0.65)
    assert r.ok and len(r.entities) == 1
    out = r.entities[0]
    assert out["confidence"] == 0.65   # capped
    assert out["self_reported_confidence"] == pytest.approx(0.92)
    # Non-numeric y point dropped; two kept.
    assert len(out["data_points"]) == 2
    assert r.dropped == 1
    # String fields normalised.
    assert out["chart_type"] == "bar"
    assert out["title"] == "Top suppliers by capacity"


def test_validate_vision_handles_missing_fields_gracefully() -> None:
    r = validate_vision({"chart_type": "line"})
    assert r.ok
    out = r.entities[0]
    assert out["chart_type"] == "line"
    assert out["title"] == ""
    assert out["data_points"] == []
    assert out["entities_mentioned"] == []
    # confidence defaults to 0.5 then caps at 0.65 → 0.5
    assert out["confidence"] == 0.5


def test_validate_vision_rejects_non_dict_payload() -> None:
    r = validate_vision("not a dict", confidence_cap=0.65)
    assert not r.ok and r.errors


# ---------- pipeline wiring ----------
class _StubVisionChat:
    """Returns one scripted vision response."""
    def __init__(self, payload: dict, model: str = "gemma4:31b"):
        self.payload = payload
        self.calls = 0
        self.model = model

    def chat_vision_json(self, *, system, user, image_bytes):
        from src.extract.client import LLMResponse
        self.calls += 1
        assert isinstance(image_bytes, (bytes, bytearray))
        return LLMResponse(text="{}", parsed=self.payload, model=self.model)


def test_pipeline_handles_image_track_and_writes_chart_card(tmp_path: Path,
                                                              monkeypatch) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    # Minimal 1x1 PNG so Pillow and vision clients can read it; we don't
    # actually open it — the stub skips image decoding.
    (inbox / "chart.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\xdac\x00\x00\x00\x02\x00\x01"
        b"\xcf\xcc\xc3\xd1\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    processed = tmp_path / "processed"

    # Stub out OllamaChat so the pipeline doesn't phone Ollama Cloud.
    from src.ingest import pipeline as _pipeline

    stub = _StubVisionChat({
        "chart_type": "bar", "title": "Suppliers",
        "x_axis_label": "Name", "y_axis_label": "Capacity",
        "x_tick_labels": ["A", "B"],
        "data_points": [{"series": "s", "x": "A", "y": 10},
                         {"series": "s", "x": "B", "y": 20}],
        "entities_mentioned": ["Horizon"],
        "description": "Two bars.", "confidence": 0.9, "notes": "",
    })

    def _fake_ollama_chat(*, host, api_key, model):
        return stub

    monkeypatch.setenv("INGEST_ENABLE_QDRANT", "0")
    monkeypatch.setenv("INGEST_ENABLE_VISION", "1")
    monkeypatch.setattr("src.ingest.pipeline.OllamaChat", _fake_ollama_chat,
                        raising=False)
    # Patch where _handle_image imports it.
    import src.extract.client as _client
    monkeypatch.setattr(_client, "OllamaChat", _fake_ollama_chat)

    cfg = _pipeline.IngestConfig(
        inbox=inbox, gold=tmp_path / "gold",
        processed_narrative=processed / "narrative",
        processed_numeric=processed / "numeric",
        audit_path=processed / "audit.sqlite",
        table_confidence_floor=0.75,
        enable_qdrant=False, qdrant_url="", qdrant_api_key=None,
        ollama_embed_host="", ollama_embed_model="", ollama_embed_dim=0,
        enable_vision=True,
        ollama_cloud_host="https://ollama.com",
        ollama_cloud_api_key="test-key",
        ollama_vision_model="gemma4:31b",
        vision_confidence_cap=0.65,
    )
    stats = _pipeline.run(cfg, force=False, log_fn=lambda _: None)
    assert stats.failures == 0
    assert stats.vision_ok == 1
    assert stats.vision_skipped_no_key == 0
    assert stub.calls == 1
    card = processed / "narrative" / "chart.md"
    assert card.exists()
    text = card.read_text()
    assert "Extraction method:** vision" in text
    assert "Confidence (capped):** 0.65" in text
    assert "Two bars." in text


def test_pipeline_skips_images_without_api_key(tmp_path: Path,
                                                 monkeypatch) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    processed = tmp_path / "processed"
    monkeypatch.setenv("INGEST_ENABLE_QDRANT", "0")
    from src.ingest.pipeline import IngestConfig, run
    cfg = IngestConfig(
        inbox=inbox, gold=tmp_path / "gold",
        processed_narrative=processed / "narrative",
        processed_numeric=processed / "numeric",
        audit_path=processed / "audit.sqlite",
        table_confidence_floor=0.75,
        enable_qdrant=False, qdrant_url="", qdrant_api_key=None,
        ollama_embed_host="", ollama_embed_model="", ollama_embed_dim=0,
        enable_vision=True,
        ollama_cloud_host="https://ollama.com",
        ollama_cloud_api_key=None,           # no key
        ollama_vision_model="gemma4:31b",
        vision_confidence_cap=0.65,
    )
    stats = run(cfg, force=False, log_fn=lambda _: None)
    assert stats.vision_ok == 0
    assert stats.vision_skipped_no_key == 1
    assert not (processed / "narrative" / "x.md").exists()
