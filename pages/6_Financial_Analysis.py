"""Financial Analysis — reported line items, calculated metrics, trends, peers.

Figures must be entered/confirmed from statements (reviewable mapping). The
engine computes metrics deterministically; missing data is shown as NOT
AVAILABLE, never zero.
"""
import pandas as pd
import streamlit as st

from src.finance.financial_data import FinancialFact, FinancialFactSet
from src.finance.comparisons import build_trend, compare_peers
from src.finance.metrics import METRIC_REGISTRY, FinancialInput, compute
from src.ui.app_state import get_app_context

st.set_page_config(page_title="Financial Analysis · FinSight AI", page_icon="📈", layout="wide")
st.title("📈 Financial Analysis")

ctx = get_app_context()

tab_calc, tab_trend, tab_peer = st.tabs(["Metric calculator", "Trend", "Peer comparison"])

with tab_calc:
    st.caption("Deterministic calculation with provenance. The LLM never computes these numbers.")
    metric_key = st.selectbox("Metric", list(METRIC_REGISTRY), format_func=lambda k: METRIC_REGISTRY[k].label)
    spec = METRIC_REGISTRY[metric_key]
    st.write("**Formula:**", spec.formula)
    inputs = {}
    cols = st.columns(len(spec.required_inputs))
    for col, slot in zip(cols, spec.required_inputs):
        with col:
            raw = st.text_input(f"{slot}", key=f"calc_{slot}", placeholder="leave blank if N/A")
            val = None
            if raw.strip():
                try:
                    val = float(raw.replace(",", ""))
                except ValueError:
                    st.error(f"'{raw}' is not a number")
            inputs[slot] = FinancialInput(name=slot, value=val)
    if st.button("Compute"):
        res = compute(metric_key, **inputs)
        if res.computed:
            st.metric(spec.label, f"{res.value:.2f} {res.unit}")
        else:
            st.warning("Not computed — " + "; ".join(res.warnings))
        if res.warnings:
            st.caption("Notes: " + "; ".join(res.warnings))
        st.caption("Result kind: CALCULATED (not a reported company figure).")

with tab_trend:
    st.caption("Enter reported figures per year; gaps are shown explicitly and never inferred.")
    company = st.text_input("Company", "Example Ltd", key="trend_co")
    metric_name = st.text_input("Line item", "revenue", key="trend_metric")
    basis = st.selectbox("Basis", ["consolidated", "standalone"], key="trend_basis")
    rows = st.data_editor(
        pd.DataFrame({"Financial Year": ["FY2021-22", "FY2022-23", "FY2023-24"],
                      "Value": [None, None, None]}),
        num_rows="dynamic", key="trend_editor", use_container_width=True)
    if st.button("Build trend"):
        fs = FinancialFactSet()
        years = []
        for _, r in rows.iterrows():
            fy = str(r["Financial Year"]).strip()
            if not fy:
                continue
            years.append(fy)
            v = r["Value"]
            if pd.notna(v):
                fs.add(FinancialFact(company, fy, metric_name, float(v), basis=basis))
        series = build_trend(fs, company, metric_name, years, basis)
        from src.ui.tables import trend_dataframe
        from src.ui.charts import line_trend
        st.dataframe(trend_dataframe(series), use_container_width=True, hide_index=True)
        st.plotly_chart(line_trend([p.financial_year for p in series.points],
                                   [p.value for p in series.points],
                                   f"{company} — {metric_name}", metric_name),
                        use_container_width=True)
        if series.warnings:
            st.warning(" ".join(series.warnings))
        st.download_button("Export CSV", trend_dataframe(series).to_csv(index=False),
                           file_name=f"{company}_{metric_name}_trend.csv")

with tab_peer:
    st.caption("Side-by-side peers for one metric & year. Mixed bases trigger a warning.")
    peers_raw = st.text_input("Companies (comma-separated)", "Example Ltd, Peer Co")
    metric_name = st.text_input("Line item", "revenue", key="peer_metric")
    fy = st.text_input("Financial year", "FY2023-24", key="peer_fy")
    editor = st.data_editor(
        pd.DataFrame({"Company": [c.strip() for c in peers_raw.split(",") if c.strip()],
                      "Value": [None] * len([c for c in peers_raw.split(",") if c.strip()]),
                      "Basis": ["consolidated"] * len([c for c in peers_raw.split(",") if c.strip()])}),
        num_rows="dynamic", key="peer_editor", use_container_width=True)
    if st.button("Compare peers"):
        fs = FinancialFactSet()
        bases = {}
        companies = []
        for _, r in editor.iterrows():
            c = str(r["Company"]).strip()
            if not c:
                continue
            companies.append(c)
            bases[c] = str(r.get("Basis") or "consolidated")
            if pd.notna(r["Value"]):
                fs.add(FinancialFact(c, fy, metric_name, float(r["Value"]), basis=bases[c]))
        pc = compare_peers(fs, companies, metric_name, fy, bases=bases)
        from src.ui.charts import bar_compare
        st.plotly_chart(bar_compare([r.company_name for r in pc.rows],
                                    [r.value for r in pc.rows],
                                    f"{metric_name} — {fy}", metric_name), use_container_width=True)
        for w in pc.warnings:
            st.warning(w)
