"""The "conversational shopping assistant" workflow — free-text chat that
lets the coordinator itself classify and route, per spec Section 4.

Relocated from app/ui/streamlit_app.py (Phase 4c implementation plan) when
the Browse Catalog page became the app's home page — this page's own logic
is otherwise unchanged, including the client-side-only transcript below.
"""

import sys
from pathlib import Path

# See app/ui/streamlit_app.py's top for why this is needed — `streamlit
# run` only puts this script's own directory on sys.path, never the
# project root, and each page here is independently executable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.ui.client import SmartshopAPIError, get_client
from app.ui.components import render_coordinator_response

st.title("💬 Conversational Shopping Assistant")
st.caption(
    "Ask about product recommendations, comparisons, reviews, or store policies — "
    "the coordinator classifies your question and routes it automatically."
)

# Client-side transcript only, for display continuity — each turn below still
# calls the stateless handle_query() with no prior-turn context. This is a
# UI convenience, not agent memory (spec Section 5 marks multi-turn memory
# out of scope; nothing here changes that).
st.session_state.setdefault("messages", [])

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["content"])
        else:
            render_coordinator_response(message["response"])

if user_query := st.chat_input("What are you looking for?"):
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.write(user_query)

    with st.chat_message("assistant"):
        try:
            response = get_client().query(user_query)
        except SmartshopAPIError as error:
            st.error(str(error))
        else:
            render_coordinator_response(response)
            st.session_state.messages.append({"role": "assistant", "response": response})
