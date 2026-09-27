"""Tests for render_coordinator_response's dispatch across all 7 CoordinatorResponse shapes.

Uses AppTest.from_function to run each call inside a real Streamlit script
context (bare calls to st.* outside one only warn/no-op) and inspect the
resulting elements — the same headless mechanism test_pages.py uses for
full pages, applied directly to the shared renderer instead.
"""

from streamlit.testing.v1 import AppTest


def _render_script(data: dict) -> None:
    from app.ui.components import render_coordinator_response

    render_coordinator_response(data)


def _run(data: dict) -> AppTest:
    at = AppTest.from_function(_render_script, kwargs={"data": data})
    at.run()
    assert not at.exception, f"render_coordinator_response raised: {at.exception}"
    return at


def test_review_summary_shape():
    at = _run({"product_id": "SP0001", "summary": "Customers like it.", "sentiment": "positive", "review_count": 3})

    assert "SP0001" in at.subheader[0].value
    assert "positive" in at.caption[0].value
    assert at.markdown[0].value == "Customers like it."


def test_recommendation_shape_with_products():
    data = {
        "rationale": "These fit your budget.",
        "products": [
            {
                "id": "SPK0012",
                "name": "SoundWave",
                "brand": "SoundCo",
                "category": "speaker",
                "price": "51.16",
                "description": "Compact design.",
                "stock": 10,
                "rating": 4.5,
            }
        ],
    }
    at = _run(data)

    assert at.markdown[0].value == "These fit your budget."
    assert "SoundWave" in at.markdown[1].value


def test_recommendation_shape_with_no_products():
    at = _run({"rationale": "Nothing matched your filters.", "products": []})

    assert at.info[0].value == "No products matched."


def test_comparison_shape():
    data = {
        "differences": ["A is cheaper", "B has a higher rating"],
        "products": [
            {
                "id": "SP0001",
                "name": "Mobile Z",
                "brand": "TechCo",
                "category": "smartphone",
                "price": "588.48",
                "description": "5G phone.",
                "stock": 43,
                "rating": 4.0,
            },
            {
                "id": "SP0004",
                "name": "SmartPhone Y",
                "brand": "RivalTech",
                "category": "smartphone",
                "price": "413.39",
                "description": "Long battery.",
                "stock": 63,
                "rating": 4.5,
            },
        ],
    }
    at = _run(data)

    markdown_values = [m.value for m in at.markdown]
    assert any("A is cheaper" in v for v in markdown_values)
    assert any("Mobile Z" in v for v in markdown_values)
    assert any("SmartPhone Y" in v for v in markdown_values)


def test_policy_shape_with_a_matched_policy():
    data = {
        "policy": {
            "policy_type": "returns",
            "description": "Laptop Return Policy",
            "conditions": ["Must be unopened"],
            "timeframe": 14,
        },
        "answer": "You have 14 days to return a laptop.",
    }
    at = _run(data)

    markdown_values = [m.value for m in at.markdown]
    assert any("Returns policy" in v for v in markdown_values)
    assert any("Must be unopened" in v for v in markdown_values)
    # st.write(str) renders as a markdown element too — the answer is the last one.
    assert at.markdown[-1].value == "You have 14 days to return a laptop."


def test_policy_shape_with_no_matched_policy():
    at = _run({"policy": None, "answer": "I don't have a specific policy on file for that."})

    # No policy-detail block (description/conditions) — just the answer itself.
    assert len(at.markdown) == 1
    assert at.markdown[0].value == "I don't have a specific policy on file for that."


def test_clarification_shape():
    at = _run({"question": "Which product are you asking about?"})

    assert at.info[0].value == "Which product are you asking about?"


def test_fallback_shape():
    # Phase 7: renders as an informational box, not a warning — the message
    # states a positive next step (what the assistant CAN do), so a
    # warning-styled box would misrepresent it, especially for a greeting.
    at = _run({"message": "I don't have a way to help with that specific request, but I can find products."})

    assert at.info[0].value == "I don't have a way to help with that specific request, but I can find products."


def test_error_shape():
    at = _run({"error": {"code": "unknown_product_id", "message": "No product with id 'SP9999'.", "sub_agent": "review_summary_agent"}})

    assert at.error[0].value == "No product with id 'SP9999'."


def test_unrecognized_shape_shows_a_generic_error_instead_of_crashing():
    at = _run({"unexpected_field": "value"})

    assert "unrecognized" in at.error[0].value.lower()


# --- Phase 5 Part A: the Product ID must be visible wherever a product is shown
# (spec: shopensemble-coordinator-agent-phase5-session-memory-spec.md, A1). The
# ID is the key every follow-up question is asked with, so a card without it
# leaves the customer unable to reuse what they were just shown.

_CARD_PRODUCTS = [
    {
        "id": "SPK0012",
        "name": "SoundWave",
        "brand": "SoundCo",
        "category": "speaker",
        "price": "51.16",
        "description": "Compact design.",
        "stock": 10,
        "rating": 4.5,
    },
    {
        "id": "LP0002",
        "name": "Ultra Thin",
        "brand": "TechCo",
        "category": "laptop",
        "price": "372.5",
        "description": "17 inch laptop.",
        "stock": 160,
        "rating": 3.7,
    },
]


def test_recommendation_cards_show_each_product_id_in_a_code_span():
    # Regression for the reported gap: cards showed name/brand/price but no ID.
    at = _run({"rationale": "Both fit.", "products": _CARD_PRODUCTS})

    markdown_values = [m.value for m in at.markdown]
    assert "**SoundWave** (SoundCo) · `SPK0012`" in markdown_values
    assert "**Ultra Thin** (TechCo) · `LP0002`" in markdown_values


def test_comparison_cards_show_each_product_id_in_a_code_span():
    at = _run({"differences": ["Different categories"], "products": _CARD_PRODUCTS})

    markdown_values = [m.value for m in at.markdown]
    assert any("`SPK0012`" in v for v in markdown_values)
    assert any("`LP0002`" in v for v in markdown_values)


def test_multiple_review_summaries_render_one_labelled_block_per_product():
    # Phase 5 spec B5: the new "summaries" response shape renders one existing
    # review-summary block per product, each headed with its Product ID.
    data = {
        "summaries": [
            {"product_id": "SP0001", "summary": "Great phone.", "sentiment": "positive", "review_count": 3},
            {"product_id": "LP0002", "summary": "Decent laptop.", "sentiment": "mixed", "review_count": 5},
        ]
    }
    at = _run(data)

    subheaders = [s.value for s in at.subheader]
    assert subheaders == ["Reviews for SP0001", "Reviews for LP0002"]
    markdown_values = [m.value for m in at.markdown]
    assert "Great phone." in markdown_values
    assert "Decent laptop." in markdown_values
