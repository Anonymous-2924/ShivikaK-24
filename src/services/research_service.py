"""Research service: simple-path retrieval + multi-agent crew orchestration."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from src.agents.crew import CrewResult, ResearchCrew
from src.rag.query_engine import Answer
from src.rag.retrieval import RetrievalFilter
from src.services.context import AppContext


@dataclass
class ResearchResponse:
    answer: Answer
    crew: Optional[CrewResult] = None


class ResearchService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    def ask(self, question: str, *, companies: list[str] | None = None,
            financial_years: list[str] | None = None, report_types: list[str] | None = None,
            use_crew: bool = False, top_k: int = 8) -> ResearchResponse:
        self.ctx.metadata_store.log_query(question)
        flt = None
        if companies or financial_years or report_types:
            flt = RetrievalFilter(company_names=companies, financial_years=financial_years,
                                  report_types=report_types)
        answer = self.ctx.engine.answer(question, top_k=top_k, flt=flt,
                                        use_llm=self.ctx.llm_available)
        crew_result = None
        if use_crew:
            crew = ResearchCrew(self.ctx.index,
                                llm_client=getattr(self.ctx.engine, "llm", None),
                                model=getattr(self.ctx.engine, "model", None))
            crew_result = crew.run(question, companies=companies, top_k=top_k)
        return ResearchResponse(answer=answer, crew=crew_result)
