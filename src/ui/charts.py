"""Plotly chart builders for the Financial Analysis page."""
from __future__ import annotations

from typing import Optional


def line_trend(years: list[str], values: list[Optional[float]], title: str, y_title: str):
    import plotly.graph_objects as go

    fig = go.Figure()
    xs = [y for y, v in zip(years, values) if v is not None]
    ys = [v for v in values if v is not None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name=y_title))
    fig.update_layout(title=title, xaxis_title="Financial Year", yaxis_title=y_title,
                      template="plotly_white", height=360, margin=dict(l=20, r=20, t=50, b=20))
    return fig


def bar_compare(labels: list[str], values: list[Optional[float]], title: str, y_title: str):
    import plotly.graph_objects as go

    pairs = [(l, v) for l, v in zip(labels, values) if v is not None]
    fig = go.Figure(go.Bar(x=[p[0] for p in pairs], y=[p[1] for p in pairs]))
    fig.update_layout(title=title, yaxis_title=y_title, template="plotly_white",
                      height=360, margin=dict(l=20, r=20, t=50, b=20))
    return fig
