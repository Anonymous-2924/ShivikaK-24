"""FinSight AI — Streamlit entrypoint.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable regardless of launch directory.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(page_title="FinSight AI", page_icon="📊", layout="wide")


from src.ui.app_state import get_app_context as _ctx


def main() -> None:
    st.title("📊 FinSight AI")
    st.caption("Financial Intelligence & Annual Report Analyst — Indian listed companies")

    try:
        ctx = _ctx()
    except Exception as exc:  # pragma: no cover - UI path
        st.error(f"Failed to initialise application context: {exc}")
        st.stop()

    from src.storage.metadata_store import MetadataStore  # noqa

    stats = ctx.metadata_store.stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Companies indexed", stats["companies"])
    c2.metric("Reports", stats["documents"])
    c3.metric("Financial years", stats["financial_years"])
    c4.metric("Indexed", stats["indexed"])

    st.divider()
    st.subheader("System status")
    col_a, col_b = st.columns(2)
    with col_a:
        st.write("**Embedding provider:**", ctx.embedder.name, f"(dim {ctx.embedder.dim})")
        st.write("**Vector store:**", f"Qdrant ({ctx.settings.qdrant_mode})")
        st.write("**Reranking:**", "ON" if ctx.rerank_status.enabled else f"OFF — {ctx.rerank_status.reason}")
    with col_b:
        st.write("**Cloud LLM (Ollama):**", "configured ✅" if ctx.llm_available else "not configured ⚠️")
        if not ctx.llm_available:
            st.info("Without a cloud LLM the app still parses, indexes and retrieves "
                    "evidence with citations. Answers are evidence-only until you set "
                    "`OLLAMA_API_KEY` on the Settings page.")

    st.divider()
    st.markdown(
        "Use the pages in the sidebar: **Dashboard**, **Company Explorer**, "
        "**Report Discovery**, **Document Management**, **AI Research**, "
        "**Financial Analysis**, **Settings**."
    )
    st.caption("Facts are grounded in indexed reports with citations. Missing or conflicting "
               "evidence is flagged; figures are never invented.")


if __name__ == "__main__":
    main()
