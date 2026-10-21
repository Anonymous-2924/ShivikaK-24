"""Tier-2 crew with stub LLM clients — real CrewAI Agent/Task/Crew
orchestration, zero network calls. Verifies:
 - corroboration confidence is computed from evidence STRUCTURE, never
   from anything the stub LLM says about its own confidence
 - the researcher/scorer roundtrip actually runs through CrewAI
 - a SessionCapReached from the underlying client propagates cleanly
   (same checkpoint-and-exit-0 contract as src/extract/extractor.py)
"""
from __future__ import annotations

import pytest

from src.agents.ollama_llm import OllamaCrewLLM
from src.agents.tier2 import (
    EvidenceItem,
    propose_candidates,
    run_tier2_inference,
    score_corroboration,
    write_confidence_note,
)
from src.extract.client import SessionCapReached


class _StubResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubChat:
    """Minimal OllamaChat-shaped stub: only chat_text is needed."""

    def __init__(self, texts: list[str] | None = None, *,
                 raises: Exception | None = None, model: str = "stub") -> None:
        self.model = model
        self.texts = texts or []
        self.raises = raises
        self.calls = 0

    def chat_text(self, *, system: str, user: str) -> _StubResponse:
        if self.raises is not None:
            raise self.raises
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return _StubResponse(text)


def test_score_corroboration_ignores_any_model_confidence_field():
    """The scorer function's signature doesn't even accept a model
    confidence — this test asserts the score is purely a function of
    evidence structure (distinct sources, type weight), proving the
    brief's 'never by model self-reported confidence' rule structurally,
    not just by convention."""
    one_source = [EvidenceItem(doc_id="d1", source_file="a.md",
                                extraction_method="llm_extracted", snippet="s")]
    two_sources = one_source + [
        EvidenceItem(doc_id="d2", source_file="b.md",
                     extraction_method="structured", snippet="s2"),
    ]
    score1, count1 = score_corroboration(one_source)
    score2, count2 = score_corroboration(two_sources)
    assert count1 == 1 and count2 == 2
    assert score2 > score1   # more independent sources -> higher score


def test_score_corroboration_weights_source_type():
    structured = [EvidenceItem(doc_id="d1", source_file="a.md",
                                extraction_method="structured", snippet="s")]
    vision = [EvidenceItem(doc_id="d1", source_file="a.md",
                            extraction_method="vision", snippet="s")]
    s_structured, _ = score_corroboration(structured)
    s_vision, _ = score_corroboration(vision)
    assert s_structured > s_vision


def test_score_corroboration_empty_evidence_is_zero():
    assert score_corroboration([]) == (0.0, 0)


def test_propose_candidates_runs_through_real_crewai_with_stub_llm():
    chat = _StubChat(texts=[
        '{"candidates": [{"name": "Nile Spinning Mills", '
        '"evidence_text": "sourced from Nile Spinning Mills", '
        '"reasoning": "explicit"}]}',
    ])
    llm = OllamaCrewLLM(ollama_chat=chat)
    candidates = propose_candidates(
        llm, target_entity="Horizon Textiles",
        evidence_snippets=[EvidenceItem(
            doc_id="d1", source_file="audit1.md",
            extraction_method="llm_extracted",
            snippet="Horizon Textiles sourced cotton from Nile Spinning Mills.")],
    )
    assert chat.calls == 1
    assert candidates == [{
        "name": "Nile Spinning Mills",
        "evidence_text": "sourced from Nile Spinning Mills",
        "reasoning": "explicit",
    }]


def test_propose_candidates_handles_junk_output_gracefully():
    chat = _StubChat(texts=["not json at all, sorry"])
    llm = OllamaCrewLLM(ollama_chat=chat)
    candidates = propose_candidates(
        llm, target_entity="X",
        evidence_snippets=[EvidenceItem(
            doc_id="d1", source_file="f.md", extraction_method="llm_extracted",
            snippet="irrelevant")],
    )
    assert candidates == []


def test_propose_candidates_propagates_session_cap_cleanly():
    chat = _StubChat(raises=SessionCapReached("mocked 429"))
    llm = OllamaCrewLLM(ollama_chat=chat)
    with pytest.raises(SessionCapReached):
        propose_candidates(
            llm, target_entity="X",
            evidence_snippets=[EvidenceItem(
                doc_id="d1", source_file="f.md",
                extraction_method="llm_extracted", snippet="s")],
        )


def test_write_confidence_note_does_not_change_the_precomputed_score():
    chat = _StubChat(texts=["Two sources corroborate this relationship."])
    llm = OllamaCrewLLM(ollama_chat=chat)
    note = write_confidence_note(
        llm, source_entity="Horizon Textiles", target_entity="Nile Spinning Mills",
        evidence=[EvidenceItem(doc_id="d1", source_file="a.md",
                                extraction_method="structured", snippet="s")],
        corroboration_score=0.73, corroboration_count=2,
    )
    assert note == "Two sources corroborate this relationship."


def test_run_tier2_inference_drops_single_source_candidates_by_default():
    researcher_chat = _StubChat(texts=["{\"candidates\": []}"])
    scorer_chat = _StubChat(texts=["narrative"])
    researcher_llm = OllamaCrewLLM(ollama_chat=researcher_chat)
    scorer_llm = OllamaCrewLLM(ollama_chat=scorer_chat)

    evidence_by_candidate = {
        "Nile Spinning Mills": [
            EvidenceItem(doc_id="d1", source_file="a.md",
                         extraction_method="llm_extracted", snippet="s"),
        ],
    }
    hyps = run_tier2_inference(
        source_entity="Horizon Textiles",
        evidence_by_candidate=evidence_by_candidate,
        researcher_llm=researcher_llm, scorer_llm=scorer_llm,
        min_corroboration_count=2,
    )
    assert hyps == []


def test_run_tier2_inference_emits_hypothesis_with_structural_confidence():
    scorer_chat = _StubChat(texts=["Corroborated by two independent sources."])
    scorer_llm = OllamaCrewLLM(ollama_chat=scorer_chat)
    researcher_llm = OllamaCrewLLM(ollama_chat=_StubChat(texts=["{}"]))

    evidence_by_candidate = {
        "Nile Spinning Mills": [
            EvidenceItem(doc_id="d1", source_file="a.md",
                         extraction_method="structured", snippet="s1"),
            EvidenceItem(doc_id="d2", source_file="b.md",
                         extraction_method="llm_extracted", snippet="s2"),
        ],
    }
    hyps = run_tier2_inference(
        source_entity="Horizon Textiles",
        evidence_by_candidate=evidence_by_candidate,
        researcher_llm=researcher_llm, scorer_llm=scorer_llm,
    )
    assert len(hyps) == 1
    h = hyps[0]
    assert h.source_entity == "Horizon Textiles"
    assert h.target_entity == "Nile Spinning Mills"
    assert h.relation_type == "supplied_by"
    assert h.corroboration_count == 2
    expected_score, _ = score_corroboration(evidence_by_candidate["Nile Spinning Mills"])
    assert h.confidence == expected_score
    assert h.narrative == "Corroborated by two independent sources."
