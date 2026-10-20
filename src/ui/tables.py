"""DataFrame helpers for the UI."""
from __future__ import annotations

from typing import Optional

import pandas as pd


def documents_dataframe(docs: list[dict]) -> pd.DataFrame:
    cols = ["company_name", "financial_year", "report_type", "basis", "parse_status",
            "index_status", "verification_status", "source_filename", "document_id"]
    if not docs:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(docs)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


def trend_dataframe(series) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Financial Year": p.financial_year,
          "Value": p.value if p.available else None,
          "Status": "reported" if p.available else "NOT AVAILABLE"}
         for p in series.points]
    )
