"""Annual Report Discovery — manual-first, honest about automated sources."""
import streamlit as st

from src.services.company_service import CompanyService
from src.ui.app_state import get_app_context

st.set_page_config(page_title="Report Discovery · FinSight AI", page_icon="🔎", layout="wide")
st.title("🔎 Annual Report Discovery")

ctx = get_app_context()
svc = CompanyService(ctx)

st.info(
    "Automated scraping of NSE/BSE/investor-relations sites is **not** enabled in this build: "
    "those sources use access controls and terms that prohibit automated bypass. The supported, "
    "reliable path is **manual**: add a report by direct URL or upload (Document Management). "
    "The provider interfaces exist so a compliant official-source adapter can be added later — "
    "see docs/data_sources.md.")

query = st.text_input("Search company (manual)")
if query:
    matches = svc.search(query)
    st.write("Candidates (from your input — not fabricated):")
    for m in matches:
        st.write(f"• {m.name} (source: {m.source}, confidence {m.confidence})")

st.divider()
st.subheader("Add a report by official URL")
with st.form("url_form"):
    company = st.text_input("Company name")
    fy = st.text_input("Financial year", placeholder="FY2023-24")
    url = st.text_input("Direct report URL (http/https)")
    exch = st.selectbox("Exchange (if known)", ["", "NSE", "BSE"])
    fast_mode = st.checkbox(
        "⚡ Fast mode (skip table detection) — recommended for large PDFs (30 MB+)", value=False)
    submitted = st.form_submit_button("Fetch & index")
if submitted:
    if not (company and fy and url):
        st.error("Company, financial year and URL are required.")
    else:
        from src.ingestion.downloader import download
        from src.services.document_service import DocumentService
        try:
            with st.spinner("Downloading (SSRF-guarded, size-limited)…"):
                res = download(url, ctx.settings.paths()["raw"],
                               max_mb=ctx.settings.max_download_mb,
                               timeout=ctx.settings.download_timeout_seconds)
            pmsg = "Indexing (fast mode)…" if fast_mode else \
                "Parsing & indexing… large PDFs with tables can take several minutes."
            with st.spinner(pmsg):
                outcome = DocumentService(ctx).add_file(
                    res.local_path, company_name=company, financial_year=fy,
                    report_type="Annual Report", source_url=url, exchange=exch or None,
                    extract_tables=not fast_mode)
            if outcome.duplicate:
                st.warning(outcome.message)
            else:
                st.success(f"{outcome.message} ({outcome.result.chunks_indexed if outcome.result else 0} chunks)")
                if outcome.result and outcome.result.parse_warnings:
                    st.warning("Parse warnings: " + "; ".join(outcome.result.parse_warnings))
        except Exception as exc:
            st.error(f"Failed: {exc}")
