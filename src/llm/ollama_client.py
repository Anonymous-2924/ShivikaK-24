"""Ollama Cloud LLM client.

Implemented against the documented Ollama REST API shape (``/api/chat``,
``/api/embed``, ``/api/tags``) with bearer authentication. The base URL and
model identifiers are fully configurable so a change to the cloud endpoint or
model names needs only a config edit, never code changes.

NOTE (verify before relying on it): the exact Ollama *Cloud* authentication and
endpoint paths should be confirmed against current official documentation for
your account. This client surfaces auth/rate-limit/unavailable errors clearly
and never fabricates a successful response.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from src.utils.errors import LLMAuthError, LLMError, LLMRateLimitError, LLMUnavailableError
from src.utils.logging import get_logger
from src.utils.retries import retry_call

log = get_logger(__name__)


@dataclass
class ChatResponse:
    text: str
    model: str
    raw: dict


class OllamaClient:
    def __init__(self, *, base_url: str, api_key: Optional[str], timeout: float = 120.0,
                 max_retries: int = 4):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        try:
            import httpx  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise LLMError(f"httpx not installed: {exc}") from exc

    @classmethod
    def from_settings(cls, settings) -> "OllamaClient":
        return cls(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key,
            timeout=settings.ollama_timeout_seconds,
            max_retries=settings.ollama_max_retries,
        )

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _client(self):
        import httpx

        return httpx.Client(timeout=self.timeout)

    def _handle_status(self, resp) -> None:
        code = resp.status_code
        if code == 401 or code == 403:
            raise LLMAuthError("Authentication failed — check OLLAMA_API_KEY.")
        if code == 429:
            raise LLMRateLimitError("Rate limit / quota exceeded on Ollama Cloud.")
        if code in (404, 503):
            raise LLMUnavailableError(f"Model or endpoint unavailable (HTTP {code}).")
        if code >= 400:
            raise LLMError(f"Ollama request failed (HTTP {code}).")

    def test_connection(self) -> dict:
        """Check connectivity/auth without generating. Never prints the key."""
        if not self.api_key:
            return {"ok": False, "reason": "No API key configured."}
        import httpx

        try:
            with self._client() as c:
                resp = c.get(f"{self.base_url}/api/tags", headers=self._headers())
            if resp.status_code in (401, 403):
                return {"ok": False, "reason": "Authentication failed."}
            if resp.status_code >= 400:
                return {"ok": False, "reason": f"HTTP {resp.status_code}."}
            data = resp.json() if resp.content else {}
            models = [m.get("name") for m in data.get("models", [])] if isinstance(data, dict) else []
            return {"ok": True, "models": models}
        except httpx.HTTPError as exc:
            return {"ok": False, "reason": f"Network error: {exc}"}

    def list_models(self) -> list[str]:
        res = self.test_connection()
        return res.get("models", []) if res.get("ok") else []

    def chat(self, model: str, prompt: str, *, system: Optional[str] = None,
             temperature: float = 0.0) -> ChatResponse:
        """Single-turn generation. Retries transient failures with backoff."""
        if not self.api_key:
            raise LLMAuthError("No OLLAMA_API_KEY configured — cannot call the cloud LLM.")
        import httpx

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "messages": messages, "stream": False,
                "options": {"temperature": temperature}}

        def _do() -> ChatResponse:
            with self._client() as c:
                resp = c.post(f"{self.base_url}/api/chat", headers=self._headers(),
                              content=json.dumps(body))
            self._handle_status(resp)
            data = resp.json()
            text = (data.get("message") or {}).get("content", "")
            return ChatResponse(text=text, model=model, raw=data)

        return retry_call(
            _do,
            retry_on=(httpx.TransportError, LLMRateLimitError, LLMUnavailableError),
            max_attempts=self.max_retries,
        )

    def embed(self, model: str, text: str) -> list[float]:
        if not self.api_key:
            raise LLMAuthError("No OLLAMA_API_KEY configured — cannot call cloud embeddings.")
        import httpx

        def _do() -> list[float]:
            with self._client() as c:
                resp = c.post(f"{self.base_url}/api/embed", headers=self._headers(),
                              content=json.dumps({"model": model, "input": text}))
            self._handle_status(resp)
            data = resp.json()
            embs = data.get("embeddings") or data.get("embedding")
            if not embs:
                raise LLMError("Embedding response contained no vector.")
            return embs[0] if isinstance(embs[0], list) else embs

        return retry_call(
            _do, retry_on=(httpx.TransportError, LLMRateLimitError), max_attempts=self.max_retries
        )
