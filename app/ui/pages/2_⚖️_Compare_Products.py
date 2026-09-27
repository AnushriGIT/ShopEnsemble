"""Product comparison — collects 2+ product IDs and composes a query."""

import sys
from pathlib import Path

# See app/ui/ShopEnsemble_App.py's top for why this is needed — `streamlit
# run` only puts this script's own directory on sys.path, never the
# project root, and each page here is independently executable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.ui.client import ShopEnsembleAPIError, get_client
from app.ui.components import render_coordinator_response

st.title("⚖️ Compare Products")
st.caption("Product IDs look like SP0001, LP0002, TV0003, SPK0012 — check the product catalog for exact IDs.")

with st.form("comparison_form"):
    ids_text = st.text_input("Product IDs (comma-separated, at least 2)", placeholder="SP0001, SP0004")
    submitted = st.form_submit_button("Compare")

if submitted:
    product_ids = [pid.strip() for pid in ids_text.split(",") if pid.strip()]
    if len(product_ids) < 2:
        st.warning("Enter at least 2 product IDs, separated by commas.")
    else:
        query_text = f"Compare {' and '.join(product_ids)}."
        with st.spinner("Comparing..."):
            try:
                response = get_client().query(query_text)
            except ShopEnsembleAPIError as error:
                st.error(str(error))
            else:
                render_coordinator_response(response)
