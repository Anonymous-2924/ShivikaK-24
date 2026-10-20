"""File validation, hashing, safe-name handling and duplicate detection.

Protects against path traversal, oversized uploads and unsupported types, and
provides SHA-256-based deduplication.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.utils.errors import ValidationError

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".md", ".txt"}

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class FileInfo:
    path: str
    filename: str
    extension: str
    size_bytes: int
    sha256: str


def safe_filename(name: str, *, max_len: int = 180) -> str:
    """Return a filesystem-safe filename, defeating path-traversal attempts.

    Strips directory components and collapses unsafe characters. Never returns
    an empty name.
    """
    # Drop any directory component (handles both / and \ and '..').
    base = os.path.basename(name.replace("\\", "/"))
    base = base.replace("..", "_")
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._") or "file"
    if len(cleaned) > max_len:
        stem, dot, ext = cleaned.rpartition(".")
        if dot and len(ext) <= 8:
            cleaned = stem[: max_len - len(ext) - 1] + "." + ext
        else:
            cleaned = cleaned[:max_len]
    return cleaned


def resolve_within(base_dir: str | Path, candidate_name: str) -> Path:
    """Resolve ``candidate_name`` strictly inside ``base_dir``.

    Raises :class:`ValidationError` if the resolved path would escape the base
    directory (defence in depth against traversal).
    """
    base = Path(base_dir).resolve()
    target = (base / safe_filename(candidate_name)).resolve()
    if base != target and base not in target.parents:
        raise ValidationError("Resolved path escapes the allowed directory.")
    return target


def sha256_file(path: str | Path, *, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


def validate_file(path: str | Path, *, max_mb: int = 200) -> FileInfo:
    """Validate a file's existence, extension and size; return its FileInfo."""
    p = Path(path)
    if not p.is_file():
        raise ValidationError(f"Not a file: {p}")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    size = p.stat().st_size
    if size == 0:
        raise ValidationError("File is empty.")
    if size > max_mb * 1024 * 1024:
        raise ValidationError(f"File exceeds the {max_mb} MB limit ({size / 1e6:.1f} MB).")
    return FileInfo(
        path=str(p), filename=p.name, extension=ext, size_bytes=size, sha256=sha256_file(p)
    )


def is_duplicate(sha256: str, known_hashes: set[str]) -> bool:
    """A file is a duplicate iff its content hash is already known."""
    return sha256 in known_hashes


def normalize_source_url(url: str) -> str:
    """Normalize a URL for duplicate detection (lowercase host, strip trailing /)."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url.strip())
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))
