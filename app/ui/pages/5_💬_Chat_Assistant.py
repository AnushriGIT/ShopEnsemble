"""The "conversational shopping assistant" workflow — free-text chat that
lets the coordinator itself classify and route, per spec Section 4.

Relocated from app/ui/ShopEnsemble_App.py (Phase 4c implementation plan) when
the Browse Catalog page became the app's home page.

Phase 5 (session memory): this is the only page that sends a ``session_id``,
so the server remembers what was already said in this conversation and a
follow-up like "review both of those" works. The four form-based pages take
explicit inputs by design and stay stateless.
"""

import sys
import uuid
from pathlib import Path

# See app/ui/ShopEnsemble_App.py's top for why this is needed — `streamlit
# run` only puts this script's own directory on sys.path, never the
# project root, and each page here is independently executable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.ui.client import ShopEnsembleAPIError, get_client
from app.ui.components import render_coordinator_response

st.title("💬 Conversational Shopping Assistant")
st.caption(
    "Ask about product recommendations, comparisons, reviews, or store policies — "
    "the coordinator classifies your question and routes it automatically."
)

# Two separate things live in session_state, and it matters which is which:
# - "messages" is the client-side transcript, for DISPLAY only — re-rendered
#   from the stored responses so IDs and cards stay visible as you scroll back.
# - "session_id" is what the SERVER uses to remember the conversation (Phase 5).
#   Generated once per browser session; a page refresh or a new tab starts a new
#   Streamlit session and therefore a new conversation — by design.
st.session_state.setdefault("messages", [])
st.session_state.setdefault("session_id", uuid.uuid4().hex)

# "New chat" runs BEFORE the transcript below is drawn, so the cleared state is
# what renders on this very run. It asks the server to forget the old session
# (best-effort — the server's idle TTL is the backstop), clears the display
# transcript, and rotates to a fresh session_id.
with st.sidebar:
    if st.button("🗑️ New chat", help="Forget this conversation and start over"):
        get_client().delete_session(st.session_state["session_id"])
        st.session_state["messages"] = []
        st.session_state["session_id"] = uuid.uuid4().hex

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
            response = get_client().query(user_query, session_id=st.session_state["session_id"])
        except ShopEnsembleAPIError as error:
            st.error(str(error))
        else:
            render_coordinator_response(response)
            st.session_state.messages.append({"role": "assistant", "response": response})
