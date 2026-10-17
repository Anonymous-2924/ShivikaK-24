"""Environment & configuration validation (no secrets printed).

Run:  python scripts/setup_check.py
"""
from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CORE = ["pydantic", "pydantic_settings", "pandas", "numpy", "pdfplumber", "openpyxl",
        "streamlit", "plotly", "qdrant_client", "rank_bm25", "httpx", "dotenv"]
OPTIONAL = ["docling", "crewai", "llama_index", "sentence_transformers", "markitdown"]


def check(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def main() -> int:
    ok = True
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        print("  ! Python 3.10+ recommended."); ok = False

    print("\nCore dependencies:")
    for m in CORE:
        present = check(m)
        print(f"  [{'OK' if present else 'MISSING'}] {m}")
        ok = ok and present

    print("\nOptional (feature-gated) dependencies:")
    for m in OPTIONAL:
        print(f"  [{'present' if check(m) else 'absent'}] {m}")

    from src.config.settings import get_settings
    s = get_settings()
    s.ensure_dirs()
    print("\nConfiguration:")
    print(f"  Ollama API key configured: {bool(s.ollama_api_key)}")  # never prints the key
    print(f"  Ollama model: {s.ollama_model}")
    print(f"  Embedding provider: {s.embedding_provider}")
    print(f"  Vector store: Qdrant ({s.qdrant_mode})")

    print("\nData directories (writable check):")
    for name, p in s.paths().items():
        p.mkdir(parents=True, exist_ok=True)
        writable = p.exists() and _writable(p)
        print(f"  [{'OK' if writable else 'FAIL'}] {name}: {p}")
        ok = ok and writable

    total, used, free = shutil.disk_usage(s.data_dir)
    print(f"\nDisk free at data dir: {free/1e9:.1f} GB")

    print("\nQdrant connectivity (embedded):")
    try:
        from src.rag.embeddings import HashingEmbedder
        from src.storage.qdrant_store import QdrantStore
        st = QdrantStore(mode="local", path=s.qdrant_path, url=None, api_key=None,
                         collection="setup_check", dim=8)
        print(f"  [OK] {st.health()}")
        st.close()
    except Exception as exc:
        print(f"  [FAIL] {exc}"); ok = False

    print("\nRESULT:", "PASS" if ok else "ISSUES FOUND")
    return 0 if ok else 1


def _writable(p: Path) -> bool:
    try:
        t = p / ".write_test"
        t.write_text("x"); t.unlink()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
