"""Company Explorer — browse indexed companies, years and coverage gaps."""
import streamlit as st

from src.services.company_service import CompanyService
from src.ui.app_state import get_app_context

st.set_page_config(page_title="Company Explorer · FinSight AI", page_icon="🏢", layout="wide")
st.title("🏢 Company Explorer")

ctx = get_app_context()
svc = CompanyService(ctx)

coverage = svc.indexed_companies()
if not coverage:
    st.info("No companies indexed yet. Add reports on the Document Management page.")
    st.stop()

names = [c.company_name for c in coverage]
sel = st.selectbox("Indexed companies", names)
chosen = next(c for c in coverage if c.company_name == sel)

c1, c2 = st.columns(2)
c1.metric("Reports", chosen.report_count)
c2.metric("Years covered", len(chosen.years))
st.write("**Financial years present:**", ", ".join(chosen.years) if chosen.years else "—")

st.divider()
st.subheader("Coverage gap check")
colA, colB = st.columns(2)
start = colA.number_input("Start year (FY start)", 2010, 2035, 2019)
end = colB.number_input("End year (FY start)", 2010, 2035, 2024)
if st.button("Check gaps"):
    gaps = svc.coverage_gaps(sel, int(start), int(end))
    if gaps:
        st.warning("Missing (not inferred): " + ", ".join(gaps))
    else:
        st.success("No gaps in the selected range.")

st.divider()
st.subheader("Reports for this company")
docs = [d for d in ctx.metadata_store.list_documents() if d["company_name"] == sel]
from src.ui.tables import documents_dataframe
st.dataframe(documents_dataframe(docs), use_container_width=True, hide_index=True)
