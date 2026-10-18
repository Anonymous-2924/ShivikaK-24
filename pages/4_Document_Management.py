"""Document Management — upload, parse, preview, re-index, delete."""
import tempfile
from pathlib import Path

import streamlit as st

from src.services.document_service import DocumentService
from src.ui.app_state import get_app_context

st.set_page_config(page_title="Documents · FinSight AI", page_icon="📁", layout="wide")
st.title("📁 Document Management")

ctx = get_app_context()
svc = DocumentService(ctx)

st.subheader("Upload a report")
with st.form("upload"):
    up = st.file_uploader("PDF / DOCX / XLSX / CSV / MD / TXT",
                          type=["pdf", "docx", "xlsx", "csv", "md", "txt"])
    company = st.text_input("Company name")
    fy = st.text_input("Financial year", placeholder="FY2023-24")
    basis = st.selectbox("Basis", ["unknown", "consolidated", "standalone"])
    report_type = st.text_input("Report type", "Annual Report")
    with st.expander("Advanced"):
        cap = st.number_input(
            "Page cap (0 = all pages)", 0, 5000, 0,
            help="Parse only the first N pages — handy to preview a huge report quickly. "
                 "Leave 0 to index the whole document (tables included).")
    go = st.form_submit_button("Upload & index")

if go:
    if not (up and company):
        st.error("A file and company name are required.")
    else:
        tmp = Path(tempfile.gettempdir()) / up.name
        tmp.write_bytes(up.getbuffer())
        try:
            bar = st.progress(0.0, text="Parsing PDF (text + tables)…")

            def _progress(done, total):
                frac = done / total if total else 0.0
                bar.progress(min(frac, 1.0), text=f"Parsing page {done}/{total} (text + tables)…")

            try:
                outcome = svc.add_file(str(tmp), company_name=company, financial_year=fy or None,
                                       report_type=report_type, basis=basis,
                                       max_pages=int(cap), progress=_progress)
            finally:
                bar.empty()
            if outcome.duplicate:
                st.warning(outcome.message)
            else:
                r = outcome.result
                st.success(f"{outcome.message} Indexed {r.chunks_indexed if r else 0} chunks.")
                if r and r.parse_warnings:
                    st.warning("Parse warnings (shown, not hidden): " + "; ".join(r.parse_warnings))
                # Markdown preview
                md_path = ctx.settings.paths()["parsed"] / f"{outcome.document.document_id}.md"
                if md_path.exists():
                    with st.expander("Extracted Markdown preview (first 3000 chars)"):
                        st.text(md_path.read_text(encoding="utf-8")[:3000])
        except Exception as exc:
            st.error(f"Failed: {exc}")

st.divider()
st.subheader("Indexed documents")
docs = svc.list_documents()
if not docs:
    st.info("No documents yet.")
else:
    from src.ui.tables import documents_dataframe
    st.dataframe(documents_dataframe(docs), use_container_width=True, hide_index=True)
    ids = [d["document_id"] for d in docs]
    target = st.selectbox("Select a document", ids,
                          format_func=lambda i: next(
                              f"{d['company_name']} · {d.get('financial_year') or '—'} · {i}"
                              for d in docs if d["document_id"] == i))
    col1, col2 = st.columns(2)
    remove_file = col2.checkbox("Also delete the original file")
    if col1.button("Remove from index", type="primary"):
        svc.delete_document(target, remove_file=remove_file)
        st.success("Removed. Original file kept unless you ticked the box.")
        st.rerun()
