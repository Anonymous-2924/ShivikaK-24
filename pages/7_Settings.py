"""Settings — connection status, model/embedding/vector-store config (secrets masked)."""
import streamlit as st

from src.ui.app_state import get_app_context, rebuild_context

st.set_page_config(page_title="Settings · FinSight AI", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")

ctx = get_app_context()
s = ctx.settings

st.subheader("Ollama Cloud (LLM generation)")
st.write("API key:", s.safe_dump()["ollama_api_key"] or "— not set —")
st.write("Base URL:", s.ollama_base_url)
st.write("Model:", s.ollama_model)
if st.button("Test connection"):
    if not s.ollama_configured():
        st.warning("No OLLAMA_API_KEY configured. Set it in your .env (never shown in full here).")
    else:
        from src.llm.ollama_client import OllamaClient
        res = OllamaClient.from_settings(s).test_connection()
        if res.get("ok"):
            st.success("Connected. Models available: " + ", ".join(res.get("models", []) or ["(none listed)"]))
        else:
            st.error("Connection failed: " + res.get("reason", "unknown"))

st.divider()
st.subheader("Embeddings")
st.write("Provider:", s.embedding_provider, "| active:", ctx.embedder.name, f"(dim {ctx.embedder.dim})")
st.write("Model:", s.embedding_model)
if ctx.embedder.name == "hashing":
    st.info("Using the dependency-free **hashing** fallback embedder. Install "
            "`sentence-transformers` and set EMBEDDING_PROVIDER=local for semantic embeddings.")

st.divider()
st.subheader("Vector store (Qdrant)")
st.json(ctx.index.store.health())

st.divider()
st.subheader("Retrieval & chunking")
col1, col2, col3 = st.columns(3)
col1.metric("Chunk size", s.chunk_size)
col2.metric("Chunk overlap", s.chunk_overlap)
col3.metric("Top-k", s.top_k)
st.write("Hybrid retrieval:", "ON" if s.hybrid_enabled else "OFF")
st.write("Reranking:", "ON" if ctx.rerank_status.enabled else f"OFF — {ctx.rerank_status.reason}")

st.divider()
st.subheader("Resources & logging")
st.write("Lightweight mode:", s.lightweight_mode, "| parse workers:", s.max_parse_workers)
st.write("Max download size (MB):", s.max_download_mb, "| log level:", s.log_level)

st.divider()
st.caption("To change settings, edit your `.env` (see .env.example) and restart the app, "
           "or use environment variables. Secrets are never displayed in full or logged.")
if st.button("Reload configuration"):
    rebuild_context()
    st.success("Configuration reloaded.")
    st.rerun()
