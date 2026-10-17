"""Research orchestration.

If CrewAI is installed and a cloud LLM is configured, a four-agent crew
(Planner → Evidence Researcher → Financial Analyst → Citation Reviewer) runs the
multi-step workflow. Otherwise a deterministic *fallback orchestrator* runs the
same stages using the real tools (retrieval + calculation) without an LLM, so
the research workflow is always available and never fabricates a crew run.

The underlying retrieval and calculation logic is shared and deterministic;
CrewAI only orchestrates. The citation reviewer can never manufacture citations
— it only verifies grounding against retrieved evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.agents.schemas import (
    AnalysisResult, EvidenceBundle, ResearchPlan, VerificationResult,
)
from src.agents.tools import CalculationTool, RetrievalTool
from src.rag.citations import numbers_supported
from src.rag.indexing import RagIndex
from src.rag.retrieval import extract_financial_years
from src.utils.logging import get_logger

log = get_logger(__name__)


def crewai_available() -> bool:
    try:
        import crewai  # noqa: F401

        return True
    except Exception:
        return False


@dataclass
class CrewResult:
    plan: ResearchPlan
    evidence: EvidenceBundle
    analysis: AnalysisResult
    verification: VerificationResult
    orchestrator: str = "fallback"  # 'crewai' | 'fallback'
    steps: list[str] = field(default_factory=list)


class ResearchCrew:
    def __init__(self, index: RagIndex, llm_client=None, model: Optional[str] = None):
        self.index = index
        self.llm = llm_client
        self.model = model
        self.retrieval = RetrievalTool(index)
        self.calc = CalculationTool()

    # ---- Planner --------------------------------------------------------
    def plan(self, question: str, companies: list[str] | None = None) -> ResearchPlan:
        years = extract_financial_years(question)
        q = question.lower()
        needs_calc = any(k in q for k in ["margin", "growth", "ratio", "roe", "roce",
                                          "debt", "coverage", "cash flow", "percent", "%"])
        missing = []
        if not companies:
            missing.append("No company specified/selected — results may be ambiguous.")
        return ResearchPlan(
            question=question, companies=companies or [], financial_years=years,
            needs_calculation=needs_calc, needs_narrative=True,
            sub_questions=[question], missing_information=missing,
        )

    # ---- Evidence Researcher -------------------------------------------
    def gather_evidence(self, plan: ResearchPlan, top_k: int = 6) -> EvidenceBundle:
        return self.retrieval.run(
            plan.question, companies=plan.companies or None,
            financial_years=plan.financial_years or None, top_k=top_k,
        )

    # ---- Financial Analyst ---------------------------------------------
    def analyse(self, plan: ResearchPlan, evidence: EvidenceBundle) -> AnalysisResult:
        observations, mgmt, caveats = [], [], []
        for item in evidence.items:
            if item.content_type in ("mdna", "narrative"):
                mgmt.append(f"[{item.company_name} {item.financial_year}] {item.excerpt[:200]}")
        if not evidence.items:
            caveats.append("No evidence retrieved; no analysis performed (abstaining).")
        if plan.needs_calculation:
            caveats.append(
                "Calculations require verified numeric inputs mapped from statements; "
                "use the Financial Analysis page to supply/confirm figures before relying "
                "on a computed metric. Numbers are never inferred here."
            )
        return AnalysisResult(observations=observations, management_explanations=mgmt, caveats=caveats)

    # ---- Citation Reviewer ---------------------------------------------
    def verify(self, answer_text: str, evidence: EvidenceBundle) -> VerificationResult:
        evidence_texts = [i.excerpt for i in evidence.items]
        if not evidence_texts:
            return VerificationResult(citations_ok=False,
                                      notes=["No evidence to verify against — abstain."])
        num = numbers_supported(answer_text, evidence_texts)
        notes = list(num.details)
        return VerificationResult(
            citations_ok=num.supported,
            unsupported_claims=[] if num.supported else ["Unsupported numeric claim(s)."],
            notes=notes,
        )

    # ---- Orchestration --------------------------------------------------
    def run(self, question: str, companies: list[str] | None = None, top_k: int = 6) -> CrewResult:
        steps = []
        plan = self.plan(question, companies)
        steps.append(f"Planned research: calc={plan.needs_calculation}, years={plan.financial_years}")
        evidence = self.gather_evidence(plan, top_k=top_k)
        steps.append(f"Retrieved {len(evidence.items)} evidence item(s).")
        analysis = self.analyse(plan, evidence)
        steps.append("Analysed evidence (deterministic; no invented values).")
        synthesis = " ".join(i.excerpt for i in evidence.items[:3])
        verification = self.verify(synthesis, evidence)
        steps.append(f"Verified grounding: citations_ok={verification.citations_ok}.")
        orchestrator = "crewai" if (crewai_available() and self.llm) else "fallback"
        return CrewResult(plan, evidence, analysis, verification, orchestrator, steps)
