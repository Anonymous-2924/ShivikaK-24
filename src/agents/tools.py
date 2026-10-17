"""Deterministic tools the agents call.

The retrieval tool is backed by the LlamaIndex/Qdrant layer (single RAG
implementation); the calculation tool is backed by the deterministic finance
engine. Tools validate inputs and return structured results — agents never do
authoritative arithmetic themselves.
"""
from __future__ import annotations

from src.agents.schemas import EvidenceBundle, EvidenceItem
from src.finance.metrics import FinancialInput, compute
from src.rag.indexing import RagIndex
from src.rag.retrieval import RetrievalFilter


class RetrievalTool:
    """Retrieve evidence from the index with optional company/FY filtering."""

    name = "retrieve_evidence"

    def __init__(self, index: RagIndex):
        self.index = index

    def run(self, query: str, *, companies=None, financial_years=None, top_k: int = 6) -> EvidenceBundle:
        flt = None
        if companies or financial_years:
            flt = RetrievalFilter(company_names=companies, financial_years=financial_years)
        chunks = self.index.retrieve(query, top_k=top_k, flt=flt, hybrid=True)
        items = [
            EvidenceItem(
                chunk_id=c.chunk_id,
                company_name=c.metadata.get("company_name", "Unknown"),
                financial_year=c.metadata.get("financial_year"),
                section=c.metadata.get("section_title"),
                page_number=c.metadata.get("page_number"),
                content_type=c.metadata.get("content_type", "narrative"),
                excerpt=(c.text[:600] + "…") if len(c.text) > 600 else c.text,
                score=c.score,
            )
            for c in chunks
        ]
        missing = [] if items else ["No evidence retrieved for this query."]
        return EvidenceBundle(items=items, missing=missing)


class CalculationTool:
    """Compute a financial metric deterministically with provenance."""

    name = "calculate_metric"

    def run(self, metric_key: str, inputs: dict[str, dict]) -> dict:
        """inputs: slot -> {value, period, basis, source_document_id, source_page}."""
        kwargs = {
            slot: FinancialInput(
                name=slot,
                value=spec.get("value"),
                period=spec.get("period"),
                basis=spec.get("basis"),
                source_document_id=spec.get("source_document_id"),
                source_page=spec.get("source_page"),
            )
            for slot, spec in inputs.items()
        }
        return compute(metric_key, **kwargs).as_dict()
