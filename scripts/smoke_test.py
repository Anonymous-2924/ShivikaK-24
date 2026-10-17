"""Optional Ollama Cloud smoke test (requires OLLAMA_API_KEY). Never prints the key.

Run:  python scripts/smoke_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import get_settings
from src.llm.ollama_client import OllamaClient


def main() -> int:
    s = get_settings()
    if not s.ollama_configured():
        print("OLLAMA_API_KEY not set — skipping cloud smoke test (this is expected offline).")
        return 0
    client = OllamaClient.from_settings(s)
    conn = client.test_connection()
    print("Connection:", "OK" if conn.get("ok") else f"FAILED ({conn.get('reason')})")
    if not conn.get("ok"):
        return 1
    try:
        resp = client.chat(s.ollama_model, "Reply with the single word: OK")
        print("Generation OK. Model:", resp.model)
        return 0
    except Exception as exc:
        print("Generation failed:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
