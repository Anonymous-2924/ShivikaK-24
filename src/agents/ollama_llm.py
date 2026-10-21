"""CrewAI LLM backend that wraps ``src.extract.client.OllamaChat``.

CrewAI agents normally talk to models through ``crewai.LLM`` (litellm).
We deliberately do NOT use that path here: litellm's exact provider
string / base_url convention for *Ollama Cloud* specifically (as opposed
to local Ollama) isn't something we could verify from this environment,
and guessing it would be exactly the kind of unverified-version mistake
the project has already been burned by once (see README). Instead this
is a thin ``crewai.llms.base_llm.BaseLLM`` subclass around the Phase 4
client, which already has session-cap detection
(``SessionCapReached``) and talks to the real Ollama Cloud endpoint.

Only ``call()`` is required by ``BaseLLM`` — everything else has sane
defaults in the base class.
"""
from __future__ import annotations

from typing import Any

from crewai.llms.base_llm import BaseLLM

from src.extract.client import OllamaChat, SessionCapReached


class OllamaCrewLLM(BaseLLM):
    """``model`` is informational only here (CrewAI requires the field);
    the actual model is whatever ``ollama_chat`` was constructed with."""

    ollama_chat: Any = None

    def __init__(self, *, ollama_chat: OllamaChat, **kwargs: Any) -> None:
        kwargs.setdefault("model", ollama_chat.model)
        super().__init__(**kwargs)
        self.ollama_chat = ollama_chat

    def call(
        self,
        messages: str | list[dict],
        tools: list[dict] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str:
        system, user = _split_messages(messages)
        res = self.ollama_chat.chat_text(system=system, user=user)
        return res.text

    def supports_function_calling(self) -> bool:
        # The tier-2 crew's agents don't use CrewAI tool-calling — they
        # read/write plain text and JSON fenced in that text. Declaring
        # this False keeps CrewAI from trying a function-calling prompt
        # shape this backend doesn't implement.
        return False


def _split_messages(messages: str | list[dict]) -> tuple[str, str]:
    """``OllamaChat`` wants one system string + one user string. CrewAI
    hands us either a bare string or a list of {"role", "content"}
    messages (system, then a growing user/assistant history). Flatten
    non-system turns into one user block, role-prefixed so the model can
    still tell them apart."""
    if isinstance(messages, str):
        return "You are a helpful assistant.", messages

    system_parts: list[str] = []
    other_parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
        else:
            other_parts.append(f"[{role}]\n{content}")

    system = "\n\n".join(system_parts) or "You are a helpful assistant."
    user = "\n\n".join(other_parts) or "(no content)"
    return system, user


__all__ = ["OllamaCrewLLM", "SessionCapReached"]
