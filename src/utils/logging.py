"""Structured logging with secret redaction.

The :class:`SecretRedactingFilter` scrubs anything that looks like an API key
or bearer token from log records so credentials never reach the logs, the UI or
exception output.
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Iterable

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"'=:\s]+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9]{8,})"),
]

_MASK = "***REDACTED***"


class SecretRedactingFilter(logging.Filter):
    """Redact secret-looking substrings from the formatted message."""

    def __init__(self, extra_secrets: Iterable[str] | None = None) -> None:
        super().__init__()
        self._extra = [s for s in (extra_secrets or []) if s]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = _redact(msg, self._extra)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def _redact(text: str, extra_secrets: list[str]) -> str:
    for secret in extra_secrets:
        if secret and secret in text:
            text = text.replace(secret, _MASK)
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: m.group(1) + _MASK, text)
    return text


_CONFIGURED = False


def configure_logging(level: str = "INFO", extra_secrets: Iterable[str] | None = None) -> None:
    """Configure root logging once. Safe to call repeatedly."""
    global _CONFIGURED
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not _CONFIGURED:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handler.addFilter(SecretRedactingFilter(extra_secrets))
        root.addHandler(handler)
        _CONFIGURED = True
    else:
        for h in root.handlers:
            for f in list(h.filters):
                if isinstance(f, SecretRedactingFilter):
                    h.removeFilter(f)
            h.addFilter(SecretRedactingFilter(extra_secrets))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
