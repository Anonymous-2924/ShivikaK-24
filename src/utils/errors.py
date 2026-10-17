"""Typed exception hierarchy for FinSight AI.

Using explicit exception types keeps error handling testable and lets the UI
present meaningful, non-sensitive messages.
"""
from __future__ import annotations


class FinSightError(Exception):
    """Base class for all application errors."""


class ConfigError(FinSightError):
    """Invalid or missing configuration."""


class ValidationError(FinSightError):
    """A supplied file, URL or value failed validation."""


class ParsingError(FinSightError):
    """A document could not be parsed."""


class IngestionError(FinSightError):
    """Indexing / ingestion failure."""


class RetrievalError(FinSightError):
    """Retrieval pipeline failure."""


class LLMError(FinSightError):
    """LLM provider failure (network, auth, rate limit, unavailable model)."""


class LLMAuthError(LLMError):
    """Authentication failed (bad or missing API key)."""


class LLMRateLimitError(LLMError):
    """Provider rate limit / quota exhausted."""


class LLMUnavailableError(LLMError):
    """Model or endpoint unavailable."""


class CalculationError(FinSightError):
    """A financial metric could not be computed from the given inputs."""


class StorageError(FinSightError):
    """Persistence layer failure."""
