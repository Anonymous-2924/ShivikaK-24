"""Tests for the Ollama client (mocked), agents, and evaluation — no network."""
import pytest

from src.config.settings import Settings
from src.llm.ollama_client import OllamaClient
from src.utils.errors import LLMAuthError, LLMRateLimitError, LLMUnavailableError


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.content = b"x"

    def json(self):
        return self._payload


def test_ollama_no_key_raises_auth():
    c = OllamaClient(base_url="https://ollama.com", api_key=None)
    with pytest.raises(LLMAuthError):
        c.chat("m", "hi")
    assert c.test_connection()["ok"] is False


def test_ollama_status_mapping():
    c = OllamaClient(base_url="https://ollama.com", api_key="k")
    with pytest.raises(LLMAuthError):
        c._handle_status(_Resp(401))
    with pytest.raises(LLMRateLimitError):
        c._handle_status(_Resp(429))
    with pytest.raises(LLMUnavailableError):
        c._handle_status(_Resp(503))


def test_ollama_chat_success(monkeypatch):
    c = OllamaClient(base_url="https://ollama.com", api_key="k")

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, content=None):
            return _Resp(200, {"message": {"content": "Revenue grew 10%."}})

    monkeypatch.setattr(c, "_client", lambda: _Client())
    resp = c.chat("gpt-oss:20b", "what happened?")
    assert "Revenue grew" in resp.text
    assert resp.model == "gpt-oss:20b"


# ---- agents crew (deterministic fallback) -------------------------------
def test_crew_plan_detects_calculation_and_years():
    from src.agents.crew import ResearchCrew

    crew = ResearchCrew(index=None)  # plan() doesn't touch the index
    plan = crew.plan("What was the operating margin in FY2023-24?", companies=["Infosys"])
    assert plan.needs_calculation
    assert "FY2023-24" in plan.financial_years
    assert plan.companies == ["Infosys"]


def test_crew_verify_rejects_unsupported_numbers():
    from src.agents.crew import ResearchCrew
    from src.agents.schemas import EvidenceBundle, EvidenceItem

    crew = ResearchCrew(index=None)
    ev = EvidenceBundle(items=[EvidenceItem(chunk_id="c", company_name="X", excerpt="PAT was 250 crore.")])
    good = crew.verify("PAT was 250 crore.", ev)
    bad = crew.verify("PAT was 999 crore.", ev)
    assert good.citations_ok
    assert not bad.citations_ok


def test_crew_verify_abstains_without_evidence():
    from src.agents.crew import ResearchCrew
    from src.agents.schemas import EvidenceBundle

    crew = ResearchCrew(index=None)
    v = crew.verify("anything", EvidenceBundle(items=[]))
    assert not v.citations_ok
