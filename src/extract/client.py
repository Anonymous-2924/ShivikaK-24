"""Ollama Cloud chat client, with session-cap awareness.

Free-tier Ollama Cloud resets its session usage every 4 hours. When the
budget runs out the server returns an HTTP-429-ish error — different
server versions phrase it differently, so we match on both status code
and message patterns. On that signal, callers should checkpoint and
exit 0 (see src/extract/checkpoint.py).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


class SessionCapReached(RuntimeError):
    """Ollama Cloud's rate / session budget was exhausted. Not a bug — resume
    on the next window."""


class ExtractionCallFailed(RuntimeError):
    """Any other transport-level failure. Caller logs and continues."""


# Signals that mean 'you have hit your free-tier budget'. We err on the side
# of treating ambiguous messages as session caps so we never bang on a
# depleted account.
_SESSION_CAP_PATTERNS = [
    re.compile(r"\b429\b"),
    re.compile(r"rate.?limit", re.I),
    re.compile(r"session (?:usage|limit|budget)", re.I),
    re.compile(r"quota", re.I),
    re.compile(r"resets? in", re.I),
]


@dataclass
class LLMResponse:
    """One raw response — parsed JSON if we could, raw text if not."""
    text: str
    parsed: dict | None
    model: str


class OllamaChat:
    def __init__(self, *, host: str, api_key: str | None, model: str,
                 temperature: float = 0.1, timeout_s: float = 120.0) -> None:
        import ollama
        self.model = model
        self.temperature = temperature
        # Ollama Cloud authenticates via Authorization header.
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = ollama.Client(host=host, headers=headers,
                                     timeout=timeout_s)

    def chat_json(self, *, system: str, user: str) -> LLMResponse:
        """Chat with ``format='json'``. Raises SessionCapReached on budget."""
        try:
            res = self.client.chat(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                format="json",
                options={"temperature": self.temperature},
            )
        except Exception as exc:   # noqa: BLE001
            msg = str(exc)
            if _looks_like_session_cap(msg):
                raise SessionCapReached(msg) from exc
            raise ExtractionCallFailed(f"{type(exc).__name__}: {msg}") from exc

        # Ollama returns {'message': {'content': '...'}, ...}
        text = (res.get("message") or {}).get("content") or ""
        parsed: dict | None = None
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                parsed = None
        except json.JSONDecodeError:
            parsed = None
        return LLMResponse(text=text, parsed=parsed, model=self.model)


def _looks_like_session_cap(msg: str) -> bool:
    return any(p.search(msg) for p in _SESSION_CAP_PATTERNS)
