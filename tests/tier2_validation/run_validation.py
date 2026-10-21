"""Tier-2 crew validation harness — INDICATIVE, NOT RIGOROUS.

Honest framing (read this before trusting any number this script prints):

 - N=2. Two fixture entries is not a statistically meaningful sample.
   This is a smoke test for the crew mechanism, not a benchmark.
 - The "evidence" is a single hand-written synthetic sentence per entry,
   not a real document. It is deliberately written to mention the known
   tier-1 and tier-2 companies the way a news snippet might, WITHOUT
   stating the tier-2 relationship as bluntly as the fixture's own
   "relationship" field does — otherwise this would test string-matching,
   not inference.
 - The fixture itself (tests/tier2_validation/fixtures/known_tier2.json)
   holds only two entries, and says plainly which one is higher-
   confidence. These are public facts I'm confident are accurate from
   general knowledge, not independently re-verified against a primary
   source in this session — the project's own ER/extraction code never
   sees this file; it exists purely to score the tier-2 crew's recall.
 - Running in real mode (the default) costs Ollama Cloud credits. This
   script is NOT invoked automatically by any CLI/Make target — you run
   it yourself, deliberately:
       python -m tests.tier2_validation.run_validation
   Pass --stub to exercise the harness mechanics with a scripted LLM and
   zero network calls / zero cost (useful for CI and for checking the
   harness itself isn't broken).

Recall here = (fixture entries whose known tier-2 name appears among the
researcher agent's proposed candidates) / (total fixture entries).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from src.agents.ollama_llm import OllamaCrewLLM
from src.agents.tier2 import EvidenceItem, propose_candidates

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "known_tier2.json"


class _StubResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubChat:
    """Deterministic stand-in so --stub never touches the network. It
    always 'finds' the known tier-2 company — it exists to prove the
    harness plumbing works, not to simulate real model accuracy."""
    model = "stub"

    def __init__(self, tier2_name: str) -> None:
        self._tier2_name = tier2_name

    def chat_text(self, *, system: str, user: str):
        payload = json.dumps({"candidates": [{
            "name": self._tier2_name,
            "evidence_text": self._tier2_name,
            "reasoning": "stub",
        }]})
        return _StubResponse(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stub", action="store_true",
                         help="Use a scripted LLM, no network calls, no cost.")
    args = parser.parse_args(argv)

    fixtures = json.loads(FIXTURE_PATH.read_text())
    host = os.environ.get("OLLAMA_CLOUD_HOST", "https://ollama.com")
    api_key = os.environ.get("OLLAMA_CLOUD_API_KEY") or None
    model = os.environ.get("OLLAMA_EXTRACT_MODEL", "gpt-oss:20b")

    if not args.stub and not api_key:
        print("OLLAMA_CLOUD_API_KEY is not set and --stub was not passed. "
              "This harness costs real Ollama Cloud credits in real mode — "
              "set the key deliberately, or pass --stub to test the "
              "harness mechanics for free.", file=sys.stderr)
        return 2

    hits = 0
    rows = []
    for entry in fixtures:
        if args.stub:
            llm = OllamaCrewLLM(ollama_chat=_StubChat(entry["known_tier2_supplier"]))
        else:
            from src.extract.client import OllamaChat
            llm = OllamaCrewLLM(ollama_chat=OllamaChat(
                host=host, api_key=api_key, model=model))

        evidence = [EvidenceItem(
            doc_id=entry["id"], source_file=f"{entry['id']}.synthetic.md",
            extraction_method="llm_extracted", snippet=entry["synthetic_passage"],
        )]
        candidates = propose_candidates(
            llm, target_entity=entry["known_tier1_supplier"],
            evidence_snippets=evidence,
        )
        found = any(
            entry["known_tier2_supplier"].lower() in c.get("name", "").lower()
            for c in candidates
        )
        hits += int(found)
        rows.append((entry["id"], entry["confidence"], found,
                      [c.get("name") for c in candidates]))

    print(f"{'id':<22} {'fixture_confidence':<20} {'recovered':<10} candidates")
    for row_id, conf, found, names in rows:
        print(f"{row_id:<22} {conf:<20} {str(found):<10} {names}")
    recall = hits / len(fixtures) if fixtures else 0.0
    print(f"\nrecall = {hits}/{len(fixtures)} = {recall:.2f}  "
          f"(N={len(fixtures)} — indicative only, see module docstring)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
