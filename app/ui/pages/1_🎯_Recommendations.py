"""Product recommendations/search — composes a natural-language query from
the form and sends it to the same POST /query every other workflow uses."""

import sys
from pathlib import Path

# See app/ui/ShopEnsemble_App.py's top for why this is needed — `streamlit
# run` only puts this script's own directory on sys.path, never the
# project root, and each page here is independently executable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.ui.client import ShopEnsembleAPIError, get_client
from app.ui.components import render_coordinator_response

st.title("🎯 Product Recommendations")

CATEGORIES = ["Any", "laptop", "smartphone", "smart_tv", "speaker"]

with st.form("recommendation_form"):
    category = st.selectbox("Category", CATEGORIES)
    max_price = st.number_input("Max price ($)", min_value=0.0, value=0.0, step=50.0)
    details = st.text_input("Anything else you're looking for? (optional)")
    submitted = st.form_submit_button("Get Recommendations")

if submitted:
    parts = ["Recommend a"]
    parts.append(category.lower() if category != "Any" else "product")
    if max_price > 0:
        parts.append(f"under ${max_price:.0f}")
    query_text = " ".join(parts) + "."
    if details:
        query_text += f" {details}"

    with st.spinner("Finding recommendations..."):
        try:
            response = get_client().query(query_text)
        except ShopEnsembleAPIError as error:
            st.error(str(error))
        else:
            render_coordinator_response(response)
