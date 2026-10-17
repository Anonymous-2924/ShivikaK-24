"""AI Research Chat — grounded answers with citations and research steps."""
import streamlit as st

from src.services.company_service import CompanyService
from src.services.research_service import ResearchService
from src.ui.app_state import get_app_context

st.set_page_config(page_title="AI Research · FinSight AI", page_icon="💬", layout="wide")
st.title("💬 AI Research")

ctx = get_app_context()
research = ResearchService(ctx)
companies = [c.company_name for c in CompanyService(ctx).indexed_companies()]

if not companies:
    st.info("Index at least one report first (Document Management).")
    st.stop()

with st.sidebar:
    st.header("Filters")
    sel_companies = st.multiselect("Companies", companies)
    fy_text = st.text_input("Financial years (comma-separated)", placeholder="FY2022-23, FY2023-24")
    use_crew = st.checkbox("Use multi-agent crew (shows research steps)", value=False)
    top_k = st.slider("Evidence passages (top-k)", 3, 15, 8)

if "history" not in st.session_state:
    st.session_state.history = []

q = st.chat_input("Ask about revenue, margins, risks, segments, cash flow…")
for role, msg in st.session_state.history:
    with st.chat_message(role):
        st.markdown(msg)

if q:
    st.session_state.history.append(("user", q))
    with st.chat_message("user"):
        st.markdown(q)
    years = [y.strip() for y in fy_text.split(",") if y.strip()] or None
    with st.chat_message("assistant"):
        with st.spinner("Researching…"):
            resp = research.ask(q, companies=sel_companies or None, financial_years=years,
                                use_crew=use_crew, top_k=top_k)
        ans = resp.answer
        if ans.abstained:
            st.warning(ans.answer_text)
        else:
            st.markdown(ans.answer_text)
            if ans.grounding_warnings:
                st.error("Grounding warnings: " + "; ".join(ans.grounding_warnings))
            st.caption("LLM synthesis: " + ("ON" if ans.llm_used else "OFF (evidence-only)"))
            with st.expander(f"Sources & evidence ({len(ans.citations)})"):
                for i, c in enumerate(ans.citations, 1):
                    st.markdown(f"**[{i}] {c.render()}**")
                    if c.source_url:
                        st.caption(f"Source URL: {c.source_url}")
                    if c.passage:
                        st.caption(c.passage)
        if resp.crew:
            with st.expander("Research steps (multi-agent)"):
                st.write("Orchestrator:", resp.crew.orchestrator)
                for s in resp.crew.steps:
                    st.write("•", s)
                if resp.crew.plan.missing_information:
                    st.warning("Missing info: " + "; ".join(resp.crew.plan.missing_information))
    st.session_state.history.append(("assistant", ans.answer_text))
