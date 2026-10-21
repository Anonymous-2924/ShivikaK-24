"""Extractor pipeline wired with stub LLM clients. Verifies:
 - proposer entity output flows into relation prompt
 - verifier is invoked for high-impact edges and sampled chunks
 - checkpoint is advanced on success, respected on rerun
 - a session-cap error short-circuits with exit-0 semantics
"""
from __future__ import annotations

from pathlib import Path

from src.extract.client import LLMResponse, SessionCapReached
from src.extract.extractor import ExtractionConfig, run


class _StubChat:
    """Returns scripted responses, in order. ``raises`` can inject exceptions
    at specific indices."""
    def __init__(self, responses: list[LLMResponse],
                 raises: dict[int, Exception] | None = None) -> None:
        self.responses = responses
        self.calls = 0
        self.raises = raises or {}

    def chat_json(self, *, system, user) -> LLMResponse:
        idx = self.calls
        self.calls += 1
        if idx in self.raises:
            raise self.raises[idx]
        return self.responses[idx]


def _write_narrative(dir_: Path, name: str, text: str) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / name).write_text(text, encoding="utf-8")


def test_pipeline_runs_proposer_then_verifier_and_checkpoints(tmp_path: Path) -> None:
    narrative = tmp_path / "narr"
    _write_narrative(
        narrative, "a.md",
        "Horizon Textiles supplied_by cotton to its plant in Dhaka.")

    # Proposer: entity call, then relation call.
    proposer = _StubChat([
        LLMResponse(
            text="{}", model="prop",
            parsed={"entities": [
                {"name": "Horizon Textiles", "type": "Supplier"},
                {"name": "Dhaka",            "type": "Geography"},
            ]}),
        LLMResponse(
            text="{}", model="prop",
            parsed={"relations": [
                {"source": "Horizon Textiles", "target": "Dhaka",
                 "type": "located_in", "confidence": 0.9,
                 "evidence_text": "plant in Dhaka"},
            ]}),
    ])
    verifier = _StubChat([
        LLMResponse(
            text="{}", model="verif",
            parsed={"verified": [
                {"index": 1, "source": "Horizon Textiles", "target": "Dhaka",
                 "type": "located_in", "verdict": "accept",
                 "confidence": 0.95},
            ]}),
    ])
    cfg = ExtractionConfig(
        narrative_dir=narrative,
        checkpoint_path=tmp_path / "extractions.jsonl",
        proposer=proposer, verifier=verifier,
        verifier_sample_rate=1.0,     # always sample
    )
    stats = run(cfg, log_fn=lambda _: None)
    assert stats.failures == 0
    assert stats.chunks_done_new == 1
    # located_in isn't high-impact, but sample_rate=1.0 forces verify.
    assert stats.verifier_calls == 1
    assert stats.relations_kept == 1

    # Second run: checkpoint says done, no further calls.
    proposer2 = _StubChat([])
    cfg2 = ExtractionConfig(
        narrative_dir=narrative,
        checkpoint_path=cfg.checkpoint_path,
        proposer=proposer2, verifier=None,
    )
    stats2 = run(cfg2, log_fn=lambda _: None)
    assert stats2.chunks_done_new == 0
    assert stats2.chunks_skipped_done == 1
    assert proposer2.calls == 0


def test_pipeline_exits_clean_on_session_cap(tmp_path: Path) -> None:
    narrative = tmp_path / "narr"
    _write_narrative(narrative, "a.md",
                      "Horizon Textiles ships via Chittagong port.")
    _write_narrative(narrative, "b.md",
                      "Monsoon Industries supplies cotton to Horizon.")

    # Proposer: entity call on first file succeeds (returns zero
    # entities so no relation call), then entity call on second file
    # raises SessionCapReached.
    proposer = _StubChat(
        responses=[
            LLMResponse(text="{}", model="p",
                        parsed={"entities": []}),
            # The second call is on file b.md — raises.
            LLMResponse(text="{}", model="p", parsed={"entities": []}),
        ],
        raises={1: SessionCapReached("mocked 429")},
    )
    cfg = ExtractionConfig(
        narrative_dir=narrative,
        checkpoint_path=tmp_path / "extractions.jsonl",
        proposer=proposer, verifier=None,
    )
    stats = run(cfg, log_fn=lambda _: None)
    assert stats.session_cap_hit is True
    # First file completed (one chunk, no entities, no relations); second
    # file aborted before any chunk succeeded.
    assert stats.chunks_done_new == 1


def test_pipeline_verifies_high_impact_edges_even_without_sample(tmp_path: Path) -> None:
    narrative = tmp_path / "narr"
    _write_narrative(narrative, "a.md",
                      "Horizon Textiles supplied by Nile Spinning Mills.")
    proposer = _StubChat([
        LLMResponse(text="{}", model="p",
                    parsed={"entities": [
                        {"name": "Horizon Textiles", "type": "Supplier"},
                        {"name": "Nile Spinning Mills", "type": "Supplier"},
                    ]}),
        LLMResponse(text="{}", model="p",
                    parsed={"relations": [
                        {"source": "Horizon Textiles",
                         "target": "Nile Spinning Mills",
                         "type": "supplied_by", "confidence": 0.8,
                         "evidence_text": "supplied by"},
                    ]}),
    ])
    verifier = _StubChat([
        LLMResponse(text="{}", model="v",
                    parsed={"verified": [
                        {"index": 1, "source": "Horizon Textiles",
                         "target": "Nile Spinning Mills",
                         "type": "supplied_by", "verdict": "accept",
                         "confidence": 0.9},
                    ]}),
    ])
    cfg = ExtractionConfig(
        narrative_dir=narrative,
        checkpoint_path=tmp_path / "extractions.jsonl",
        proposer=proposer, verifier=verifier,
        verifier_sample_rate=0.0,   # NO random sampling
    )
    stats = run(cfg, log_fn=lambda _: None)
    # supplied_by is high-impact → verifier runs regardless of sample_rate.
    assert stats.verifier_calls == 1
    assert stats.relations_kept == 1
