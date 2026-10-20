"""Tier-2 inference crew (researcher -> corroborator -> confidence-scorer).

This is the one place in the project CrewAI earns its keep (brief rule:
"do not make everything an agent just because the framework is
available" — the ingestion pipeline and the Phase 5 router are both
deterministic for exactly that reason). Inferring an unstated tier-2
supplier relationship from scattered, imperfect evidence is genuinely a
multi-step reasoning task, not a lookup.

**Critical brief rule**: corroboration is scored by STRUCTURE — count of
independent sources, source-type reliability, recency — never by a
model's self-reported confidence. So the LLM agents here only ever (a)
extract candidate relationships + their evidence spans from text, and
(b) write the final narrative. The number that actually becomes
``Hypothesis.confidence`` is computed in plain Python by
``score_corroboration()``, never asked of or accepted from the model.

Output is written to the graph as ``extraction_method="inferred"`` edges
with ``is_hypothesis=True`` (an extra prop; the schema validator in
``src/graph/schema.py`` only checks required fields are present, so this
needs no schema change) so Phase 8's UI can render them dashed/dim.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from src.agents.ollama_llm import OllamaCrewLLM
from src.extract.client import OllamaChat, SessionCapReached

# Source-type reliability weights for corroboration scoring. Structured
# ERP data and hand-verified gold tables are closer to ground truth than
# a proposer's unverified read of a chunk; vision reads of charts are the
# least reliable (confidence-capped at 0.65 for the same reason at
# ingest time — see src/extract/vision.py).
_SOURCE_TYPE_WEIGHT = {
    "structured": 1.0,
    "manual": 1.0,
    "llm_extracted": 0.7,
    "vision": 0.5,
    "inferred": 0.4,   # a hypothesis corroborating another hypothesis counts less
}
_RECENCY_HALF_LIFE_DAYS = 365.0


@dataclass(frozen=True)
class EvidenceItem:
    doc_id: str
    source_file: str
    extraction_method: str
    snippet: str
    as_of: str | None = None   # ISO date if known; None if undated


@dataclass
class Hypothesis:
    source_entity: str
    target_entity: str
    relation_type: str
    confidence: float
    corroboration_count: int
    evidence: list[EvidenceItem] = field(default_factory=list)
    narrative: str = ""


def score_corroboration(evidence: list[EvidenceItem], *,
                         today: date | None = None) -> tuple[float, int]:
    """Deterministic corroboration score in [0, 1], plus the independent-
    source count it was built from. NOT derived from any model output.

    independent sources = distinct (source_file) count.
    Each source contributes its type-reliability weight, decayed by age
    (half-life ``_RECENCY_HALF_LIFE_DAYS``; undated evidence gets no
    decay — we have no information to penalise it with). The combined
    score is ``1 - product(1 - w_i)`` over distinct sources — i.e. more
    independent corroborating sources raise confidence, with diminishing
    returns, and one weak source alone never maxes it out.
    """
    today = today or date.today()
    by_source: dict[str, EvidenceItem] = {}
    for e in evidence:
        # Keep the strongest-typed evidence item per distinct source file.
        prev = by_source.get(e.source_file)
        if prev is None or (_SOURCE_TYPE_WEIGHT.get(e.extraction_method, 0.3)
                             > _SOURCE_TYPE_WEIGHT.get(prev.extraction_method, 0.3)):
            by_source[e.source_file] = e

    if not by_source:
        return 0.0, 0

    complement = 1.0
    for e in by_source.values():
        w = _SOURCE_TYPE_WEIGHT.get(e.extraction_method, 0.3)
        if e.as_of:
            try:
                age_days = (today - _parse_date(e.as_of)).days
                # Half-life decay: weight *= 0.5 ** (age_days / half_life).
                w *= 0.5 ** (max(age_days, 0) / _RECENCY_HALF_LIFE_DAYS)
            except ValueError:
                pass
        complement *= (1.0 - min(max(w, 0.0), 1.0))
    score = round(1.0 - complement, 4)
    return score, len(by_source)


def _parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


# ---------------------------------------------------------------------
# Crew assembly
# ---------------------------------------------------------------------
RESEARCHER_SYSTEM = (
    "You are a supply-chain research analyst. You are given raw text "
    "snippets that mention a known entity. Your job is to spot mentions "
    "of OTHER companies that might be its tier-2 (sub-)supplier, based "
    "only on what the text actually says. You never invent a company "
    "name that isn't in the text. Respond with STRICT JSON only:\n"
    '{"candidates": [{"name": "<company name verbatim from text>", '
    '"evidence_text": "<verbatim short span>", "reasoning": "<1 sentence>"}]}\n'
    'If you find nothing, respond {"candidates": []}.'
)

SCORER_SYSTEM = (
    "You write a short, neutral analyst note summarizing a hypothesized "
    "tier-2 supplier relationship. You are given the candidate "
    "relationship, its evidence snippets, and a corroboration score that "
    "was already computed from the evidence's structure (number of "
    "independent sources, their reliability, their age) — NOT by you. "
    "Do not invent your own confidence number; just explain, in 2-4 "
    "sentences, what the evidence shows and how many independent "
    "sources support it. Respond with plain text, no JSON."
)


def build_researcher_agent(llm: OllamaCrewLLM):
    from crewai import Agent
    return Agent(
        role="Supply Chain Researcher",
        goal="Find textual evidence of undisclosed tier-2 supplier relationships",
        backstory="A meticulous analyst who never states a fact the source text "
                   "does not support.",
        llm=llm, verbose=False,
    )


def build_scorer_agent(llm: OllamaCrewLLM):
    from crewai import Agent
    return Agent(
        role="Confidence Note Writer",
        goal="Explain a pre-scored corroboration finding in plain language",
        backstory="A careful writer who reports what the evidence shows without "
                   "second-guessing the structural score it was given.",
        llm=llm, verbose=False,
    )


def propose_candidates(researcher_llm: OllamaCrewLLM, *, target_entity: str,
                        evidence_snippets: list[EvidenceItem]) -> list[dict]:
    """Researcher pass: extract candidate tier-2 names + evidence from text.

    Runs the researcher Agent/Task through a one-task Crew. Returns a
    list of ``{"name", "evidence_text", "reasoning"}`` dicts (possibly
    empty). Raises ``SessionCapReached`` unchanged so callers can
    checkpoint, same convention as ``src/extract/extractor.py``.
    """
    from crewai import Crew, Process, Task

    agent = build_researcher_agent(researcher_llm)
    snippet_block = "\n\n".join(
        f"[source={e.source_file}]\n{e.snippet}" for e in evidence_snippets
    ) or "(no snippets provided)"
    task = Task(
        description=(
            f"{RESEARCHER_SYSTEM}\n\n"
            f"KNOWN ENTITY: {target_entity}\n\n"
            f"TEXT SNIPPETS:\n---\n{snippet_block}\n---"
        ),
        expected_output="A JSON object with a 'candidates' array.",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential,
                verbose=False)
    try:
        result = crew.kickoff()
    except Exception as exc:   # noqa: BLE001
        raise _unwrap_session_cap(exc) from exc
    return _parse_candidates(str(result))


def write_confidence_note(scorer_llm: OllamaCrewLLM, *, source_entity: str,
                           target_entity: str, evidence: list[EvidenceItem],
                           corroboration_score: float,
                           corroboration_count: int) -> str:
    """Confidence-scorer pass: narrative only — the confidence number is
    already fixed by ``score_corroboration()`` before this is called."""
    from crewai import Crew, Process, Task

    agent = build_scorer_agent(scorer_llm)
    evidence_block = "\n".join(
        f"- [{e.source_file} / {e.extraction_method}] {e.snippet}"
        for e in evidence
    ) or "(no evidence)"
    task = Task(
        description=(
            f"{SCORER_SYSTEM}\n\n"
            f"CANDIDATE RELATIONSHIP: {source_entity} is possibly tier-2-"
            f"supplied by {target_entity}.\n"
            f"CORROBORATION SCORE (already computed, do not change): "
            f"{corroboration_score:.2f} from {corroboration_count} "
            f"independent source(s).\n\n"
            f"EVIDENCE:\n{evidence_block}"
        ),
        expected_output="2-4 sentences of plain text.",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential,
                verbose=False)
    try:
        result = crew.kickoff()
    except Exception as exc:   # noqa: BLE001
        raise _unwrap_session_cap(exc) from exc
    return str(result).strip()


def run_tier2_inference(*, source_entity: str, evidence_by_candidate: dict[str, list[EvidenceItem]],
                         researcher_llm: OllamaCrewLLM,
                         scorer_llm: OllamaCrewLLM,
                         min_corroboration_count: int = 1) -> list[Hypothesis]:
    """Given evidence already grouped by candidate tier-2 name (the
    caller does retrieval — e.g. via ``src.retrieve.semantic`` — this
    function does not scan a corpus itself), score each candidate and
    write its narrative. Candidates below ``min_corroboration_count``
    independent sources are dropped — a single unverified mention is not
    a hypothesis worth putting in the graph."""
    hypotheses: list[Hypothesis] = []
    for candidate_name, items in evidence_by_candidate.items():
        score, count = score_corroboration(items)
        if count < min_corroboration_count:
            continue
        narrative = write_confidence_note(
            scorer_llm, source_entity=source_entity, target_entity=candidate_name,
            evidence=items, corroboration_score=score, corroboration_count=count,
        )
        hypotheses.append(Hypothesis(
            source_entity=source_entity, target_entity=candidate_name,
            relation_type="supplied_by", confidence=score,
            corroboration_count=count, evidence=items, narrative=narrative,
        ))
    return hypotheses


def _unwrap_session_cap(exc: BaseException, *, max_depth: int = 8) -> BaseException:
    """CrewAI's internal executor may catch our SessionCapReached and
    re-raise it wrapped in its own exception type. Walk __cause__/
    __context__ to find the original and surface that instead, so
    callers can checkpoint on it exactly like src/extract/extractor.py
    does for the Phase 4 proposer/verifier calls. Falls back to ``exc``
    itself if no SessionCapReached is found in the chain."""
    current: BaseException | None = exc
    for _ in range(max_depth):
        if isinstance(current, SessionCapReached):
            return current
        if current is None:
            break
        current = current.__cause__ or current.__context__
    return exc


def _parse_candidates(text: str) -> list[dict]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return []
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    cands = obj.get("candidates", [])
    return [c for c in cands if isinstance(c, dict) and c.get("name")]


def make_crew_llms(
    *, host: str, api_key: str | None, researcher_model: str, scorer_model: str,
) -> tuple[OllamaCrewLLM, OllamaCrewLLM]:
    """Convenience constructor wiring both crew roles to Ollama Cloud,
    reusing the same client/session-cap plumbing as Phase 4 extraction."""
    researcher = OllamaCrewLLM(ollama_chat=OllamaChat(
        host=host, api_key=api_key, model=researcher_model))
    scorer = OllamaCrewLLM(ollama_chat=OllamaChat(
        host=host, api_key=api_key, model=scorer_model))
    return researcher, scorer
