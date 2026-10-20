"""CrewAI agent/task definitions (constructed only when CrewAI is installed).

These factory functions build the four agents and their tasks against the
*documented* CrewAI API. They are invoked by the orchestrator only when
``crewai`` is importable and a cloud LLM is configured; otherwise the
deterministic fallback in :mod:`src.agents.crew` runs the same stages.

Iteration limits and delegation are constrained to prevent unbounded loops.
"""
from __future__ import annotations

AGENT_SPECS = {
    "planner": {
        "role": "Research Planner",
        "goal": "Interpret the question, identify companies/years, and decide what evidence and "
                "calculations are required.",
        "backstory": "A meticulous equity research lead who scopes work before any retrieval.",
    },
    "researcher": {
        "role": "Financial Evidence Researcher",
        "goal": "Retrieve the most relevant annual-report sections and tables with exact source "
                "metadata; report conflicts and gaps explicitly.",
        "backstory": "A diligent analyst who only reports what the documents say.",
    },
    "analyst": {
        "role": "Financial Analyst",
        "goal": "Use deterministic calculation tools for numbers; separate observed changes from "
                "management explanations and never infer causality from correlation.",
        "backstory": "A CFA-style analyst who never invents figures.",
    },
    "reviewer": {
        "role": "Citation & Verification Reviewer",
        "goal": "Confirm every material claim is supported by retrieved evidence and reject "
                "fabricated or incomplete citations.",
        "backstory": "A sceptical reviewer who would rather mark a claim unverified than let an "
                     "unsupported statement through.",
    },
}


def build_crew(llm, tools: dict, *, max_iter: int = 4, verbose: bool = False):
    """Build a CrewAI Crew. Raises ImportError if crewai is not installed."""
    from crewai import Agent, Crew, Process, Task  # noqa

    def _agent(key):
        s = AGENT_SPECS[key]
        return Agent(role=s["role"], goal=s["goal"], backstory=s["backstory"],
                     llm=llm, max_iter=max_iter, allow_delegation=False, verbose=verbose)

    planner = _agent("planner")
    researcher = _agent("researcher")
    analyst = _agent("analyst")
    reviewer = _agent("reviewer")

    tplan = Task(description="Create a research plan for: {question}",
                 expected_output="A structured plan: companies, years, calc/narrative needs, gaps.",
                 agent=planner)
    tresearch = Task(description="Retrieve evidence for the plan using the retrieval tool.",
                     expected_output="Structured findings with exact source metadata.",
                     agent=researcher, context=[tplan])
    tanalyse = Task(description="Analyse evidence; compute metrics via the calculation tool only.",
                    expected_output="Observations, calculated metrics with provenance, caveats.",
                    agent=analyst, context=[tresearch])
    treview = Task(description="Verify grounding and citations; flag unsupported claims.",
                   expected_output="Verification result with any unsupported claims listed.",
                   agent=reviewer, context=[tanalyse])

    return Crew(agents=[planner, researcher, analyst, reviewer],
                tasks=[tplan, tresearch, tanalyse, treview],
                process=Process.sequential, verbose=verbose)
