"""Pydantic schemas exchanged between agents.

Agents pass concise structured findings — never whole annual reports — so the
LLM context stays small and the hand-offs stay validated.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ResearchPlan(BaseModel):
    question: str
    companies: list[str] = Field(default_factory=list)
    financial_years: list[str] = Field(default_factory=list)
    needs_calculation: bool = False
    needs_narrative: bool = True
    sub_questions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    chunk_id: str
    company_name: str
    financial_year: Optional[str] = None
    section: Optional[str] = None
    page_number: Optional[int] = None
    content_type: str = "narrative"
    excerpt: str
    score: float = 0.0


class EvidenceBundle(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    observations: list[str] = Field(default_factory=list)
    calculated_metrics: list[dict] = Field(default_factory=list)
    management_explanations: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    verified_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    citations_ok: bool = True
    notes: list[str] = Field(default_factory=list)
