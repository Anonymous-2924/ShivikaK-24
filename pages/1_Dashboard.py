"""Dashboard page — all metrics come from real application state."""
import streamlit as st

from src.ui.app_state import get_app_context

st.set_page_config(page_title="Dashboard · FinSight AI", page_icon="📊", layout="wide")
st.title("📊 Dashboard")

ctx = get_app_context()
stats = ctx.metadata_store.stats()

c1, c2, c3 = st.columns(3)
c1.metric("Companies indexed", stats["companies"])
c2.metric("Annual reports", stats["documents"])
c3.metric("Financial years covered", stats["financial_years"])
c4, c5, c6 = st.columns(3)
c4.metric("Indexed successfully", stats["indexed"])
c5.metric("Failed ingestions", stats["failed"])
c6.metric("Vector chunks", ctx.index.store.count())

st.divider()
st.subheader("Recent research queries")
recent = ctx.metadata_store.recent_queries(10)
if recent:
    for q in recent:
        st.write("•", q)
else:
    st.caption("No queries yet. Ask something on the AI Research page.")

st.divider()
st.subheader("Ingestion & parsing status")
docs = ctx.metadata_store.list_documents()
if docs:
    from src.ui.tables import documents_dataframe

    st.dataframe(documents_dataframe(docs), use_container_width=True, hide_index=True)
else:
    st.info("No documents yet. Add one on the Document Management page.")
