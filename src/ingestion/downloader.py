"""Safe HTTP(S) downloader with SSRF protection, size and timeout limits.

Only http/https are permitted; private/loopback/link-local hosts are blocked.
Files are streamed to disk with a hard size cap and the content hash is
computed so duplicates can be detected before indexing.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from src.ingestion.file_validation import safe_filename, sha256_file
from src.utils.errors import ValidationError
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class DownloadResult:
    local_path: str
    sha256: str
    size_bytes: int
    source_url: str


def validate_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise ValidationError(f"Only http/https URLs are allowed (got '{parts.scheme}').")
    if not parts.hostname:
        raise ValidationError("URL has no host.")
    _assert_public_host(parts.hostname)
    return url


def _assert_public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValidationError(f"Cannot resolve host '{host}': {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValidationError(f"Refusing to connect to non-public address {ip} (SSRF guard).")


def download(url: str, dest_dir: str | Path, *, max_mb: int = 200, timeout: float = 60.0,
             filename: str | None = None) -> DownloadResult:
    """Download a URL to ``dest_dir`` safely. Requires ``httpx`` or ``requests``."""
    validate_url(url)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = safe_filename(filename or Path(urlsplit(url).path).name or "download.bin")
    dest = dest_dir / name
    max_bytes = max_mb * 1024 * 1024

    client = _http_client()
    written = 0
    # Some corporate CDNs reject requests without browser-like headers (HTTP 406).
    # Sending a normal Accept/User-Agent is standard client identification, not an
    # access-control bypass.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 FinSightAI/0.1"
        ),
        "Accept": "application/pdf,application/octet-stream,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with client.stream("GET", url, timeout=timeout, follow_redirects=True,
                       headers=headers) as resp:  # type: ignore
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_bytes():
                written += len(chunk)
                if written > max_bytes:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise ValidationError(f"Download exceeded {max_mb} MB limit.")
                fh.write(chunk)
    return DownloadResult(str(dest), sha256_file(dest), written, url)


def _http_client():
    try:
        import httpx

        return httpx.Client()
    except Exception as exc:  # pragma: no cover
        raise ValidationError(f"HTTP client (httpx) unavailable: {exc}") from exc
