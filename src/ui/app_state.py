"""Shared Streamlit state: one cached AppContext reused across all pages."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st


@st.cache_resource(show_spinner="Initialising FinSight AI…")
def get_app_context():
    from src.services.context import build_context

    return build_context()


def rebuild_context():
    get_app_context.clear()
    return get_app_context()
