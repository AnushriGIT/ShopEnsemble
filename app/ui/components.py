"""Shared rendering for every ``CoordinatorResponse`` shape.

The UI only ever sees JSON (via ``client.py``), not typed Python objects, so
``render_coordinator_response`` dispatches on which keys are present rather
than an ``isinstance`` check. The 8 response shapes never overlap on their
first distinguishing key, so a plain elif chain is unambiguous:

- ``error``       -> AgentErrorEnvelope
- ``summaries``   -> ReviewSummariesResponse (2+ products; Phase 5)
- ``sentiment``   -> ReviewSummaryResponse
- ``rationale``   -> RecommendationResponse
- ``differences`` -> ComparisonResponse
- ``policy``      -> PolicyResponse (always present, even when null — Pydantic serializes every field)
- ``question``    -> ClarificationResponse
- ``message``     -> FallbackResponse

One shared function, not one per page, so every workflow renders a given
response type identically.
"""

import streamlit as st


def render_coordinator_response(data: dict) -> None:
    if "error" in data:
        _render_error(data)
    elif "summaries" in data:
        _render_review_summaries(data)
    elif "sentiment" in data:
        _render_review_summary(data)
    elif "rationale" in data:
        _render_recommendation(data)
    elif "differences" in data:
        _render_comparison(data)
    elif "policy" in data:
        _render_policy(data)
    elif "question" in data:
        _render_clarification(data)
    elif "message" in data:
        _render_fallback(data)
    else:
        st.error("Received an unrecognized response shape from the API.")


def _render_review_summary(data: dict) -> None:
    st.subheader(f"Reviews for {data['product_id']}")
    st.caption(f"{data['review_count']} review(s) — sentiment: **{data['sentiment']}**")
    st.write(data["summary"])


def _render_review_summaries(data: dict) -> None:
    # One existing single-product block per product, in the order returned
    # (request order), each headed with its Product ID.
    for summary in data["summaries"]:
        _render_review_summary(summary)


def _render_recommendation(data: dict) -> None:
    st.write(data["rationale"])
    products = data["products"]
    if not products:
        st.info("No products matched.")
        return
    for product in products:
        _render_product_card(product)


def _render_comparison(data: dict) -> None:
    st.markdown("**Differences:**")
    for difference in data["differences"]:
        st.markdown(f"- {difference}")
    products = data["products"]
    columns = st.columns(len(products)) if products else []
    for column, product in zip(columns, products, strict=True):
        with column:
            _render_product_card(product)


def _render_policy(data: dict) -> None:
    policy = data["policy"]
    if policy is not None:
        st.markdown(f"**{policy['policy_type'].replace('_', ' ').title()} policy**")
        st.markdown(f"_{policy['description']}_ ({policy['timeframe']} days)")
        for condition in policy["conditions"]:
            st.markdown(f"- {condition}")
        st.divider()
    st.write(data["answer"])


def _render_clarification(data: dict) -> None:
    st.info(data["question"])


def _render_fallback(data: dict) -> None:
    # Phase 7: an informational box, not a warning — every fallback message
    # now states a positive next step (what the assistant CAN do), including a
    # plain greeting reply, so a warning-styled box would misrepresent it.
    st.info(data["message"])


def _render_error(data: dict) -> None:
    # data["error"]["message"] is always a safe, displayable message — the
    # API's global exception handler never lets a raw exception through.
    st.error(data["error"]["message"])


def _render_product_card(product: dict) -> None:
    """Render one product as a bordered card.

    The Product ID is shown in a code span on the header line (Phase 5 spec,
    Part A1). It is the key every follow-up question is asked with — compare
    it, summarize its reviews — so a card without it leaves the customer
    unable to reuse what they were just shown. It's rendered here,
    deterministically, from the catalog record, so it can never be missing
    because a model omitted it from generated text.
    """

    with st.container(border=True):
        st.markdown(f"**{product['name']}** ({product['brand']}) · `{product['id']}`")
        st.caption(f"{product['category']} — ${product['price']} — rating {product['rating']}/5")
        st.write(product["description"])
