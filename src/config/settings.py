"""Centralised application configuration for FinSight AI.

All runtime configuration is read from environment variables (optionally via a
``.env`` file) using Pydantic settings. Secrets (API keys) are never logged or
rendered; :meth:`Settings.safe_dump` masks them explicitly.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (src/config/settings.py -> repo root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Application settings.

    Values can be overridden via environment variables (prefix-free) or a
    ``.env`` file in the project root. See ``.env.example`` for the full list.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Ollama Cloud (LLM generation) ----------------------------------
    ollama_api_key: str | None = Field(default=None, description="Ollama Cloud API key.")
    ollama_base_url: str = Field(
        default="https://ollama.com",
        description="Base URL for the Ollama-compatible cloud endpoint.",
    )
    ollama_model: str = Field(
        default="gpt-oss:20b",
        description="Default generation model identifier (configurable per account).",
    )
    ollama_timeout_seconds: float = 120.0
    ollama_max_retries: int = 4
    ollama_concurrency: int = 1  # conservative default for free-tier rate limits

    # ---- Embeddings -----------------------------------------------------
    embedding_provider: Literal["local", "ollama", "hashing"] = Field(
        default="local",
        description="local=sentence-transformers, ollama=cloud, hashing=dependency-free fallback.",
    )
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384  # must match the chosen model; validated at index time
    embedding_batch_size: int = 32

    # ---- Vector store ---------------------------------------------------
    vector_store: Literal["qdrant"] = "qdrant"
    qdrant_mode: Literal["local", "server"] = Field(
        default="local",
        description="local=embedded on-disk Qdrant; server=connect to a running instance.",
    )
    qdrant_path: str = str(DATA_DIR / "qdrant")
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "finsight_reports"

    # ---- Retrieval / chunking ------------------------------------------
    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 8
    hybrid_enabled: bool = True
    rerank_enabled: bool = False  # off unless a compatible reranker is installed

    # ---- Resource limits (16 GB machine defaults) -----------------------
    lightweight_mode: bool = True
    max_parse_workers: int = 1
    max_download_mb: int = 200
    download_timeout_seconds: float = 120.0

    # ---- PDF parsing performance ---------------------------------------
    # Table detection is the slow part of pdfplumber on large reports. Turn it
    # off for a fast text-only pass, or cap how many pages get the table pass.
    pdf_extract_tables: bool = True
    pdf_max_pages: int = 0  # 0 = all pages; >0 caps pages parsed (with a warning)

    # ---- Storage paths --------------------------------------------------
    data_dir: str = str(DATA_DIR)
    metadata_db_path: str = str(DATA_DIR / "metadata" / "finsight.db")

    # ---- Logging / cache ------------------------------------------------
    log_level: str = "INFO"
    cache_enabled: bool = True

    _SECRET_FIELDS = {"ollama_api_key", "qdrant_api_key"}

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    def paths(self) -> dict[str, Path]:
        base = Path(self.data_dir)
        return {
            "data": base,
            "raw": base / "raw",
            "parsed": base / "parsed",
            "metadata": base / "metadata",
            "evaluations": base / "evaluations",
            "exports": base / "exports",
            "qdrant": Path(self.qdrant_path),
            "cache": base / "cache",
        }

    def ensure_dirs(self) -> None:
        """Create all required data directories (idempotent)."""
        for p in self.paths().values():
            p.mkdir(parents=True, exist_ok=True)
        Path(self.metadata_db_path).parent.mkdir(parents=True, exist_ok=True)

    def ollama_configured(self) -> bool:
        return bool(self.ollama_api_key)

    def safe_dump(self) -> dict[str, Any]:
        """Return settings with secrets masked — safe for logs and the UI."""
        data = self.model_dump()
        for key in self._SECRET_FIELDS:
            val = data.get(key)
            data[key] = _mask(val) if val else None
        return data


def _mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}…{secret[-2:]} (masked)"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads env/.env once)."""
    s = Settings()
    return s


def reload_settings() -> Settings:
    """Clear the cache and re-read configuration (used by the Settings page)."""
    get_settings.cache_clear()
    # Reload dotenv values that may have been written at runtime.
    return get_settings()
