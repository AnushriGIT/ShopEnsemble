"""Review summaries and sentiment insights for a single product."""

import sys
from pathlib import Path

# See app/ui/streamlit_app.py's top for why this is needed — `streamlit
# run` only puts this script's own directory on sys.path, never the
# project root, and each page here is independently executable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.ui.client import SmartshopAPIError, get_client
from app.ui.components import render_coordinator_response

st.title("⭐ Review Summaries")
st.caption("Product IDs look like SP0001, LP0002, TV0003, SPK0012 — check the product catalog for exact IDs.")

with st.form("review_form"):
    product_id = st.text_input("Product ID", placeholder="SP0001")
    submitted = st.form_submit_button("Summarize Reviews")

if submitted:
    if not product_id.strip():
        st.warning("Enter a product ID.")
    else:
        query_text = f"What do people say about {product_id.strip()}?"
        with st.spinner("Summarizing reviews..."):
            try:
                response = get_client().query(query_text)
            except SmartshopAPIError as error:
                st.error(str(error))
            else:
                render_coordinator_response(response)
