"""AppTest-based smoke tests: each page loads without exception, submitting
its form triggers the (mocked) client call with the expected composed
query, and the response renders. Real client calls never happen — see
conftest.py's ``fake_client_factory``.
"""

from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

# AppTest.from_file resolves a relative path against the *calling* file's own
# directory, not the cwd — found by actually running this (Rule 9), not
# assumed. Build absolute paths from the project root instead.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SAMPLE_PRODUCTS = [
    {
        "id": "SP0001",
        "name": "Mobile Z",
        "brand": "TechCo",
        "category": "smartphone",
        "price": "588.48",
        "description": "Smartphone with 5G connectivity.",
        "stock": 43,
        "rating": 4.0,
    },
    {
        "id": "LP0002",
        "name": "Laptop Pro",
        "brand": "ByteWorks",
        "category": "laptop",
        "price": "999.99",
        "description": "Lightweight laptop for professionals.",
        "stock": 10,
        "rating": 4.5,
    },
]


def _app_test(relative_path: str) -> AppTest:
    return AppTest.from_file(str(_PROJECT_ROOT / relative_path))


def test_catalog_page_loads_and_shows_every_product(fake_client_factory):
    # st.cache_data is a process-wide cache keyed by function args (none
    # here) — without clearing it, a prior test's fake products would still
    # be served here, same class of test-isolation bug Phase 4b hit with
    # the API's TTLCache. Cleared at the start of every catalog test below.
    st.cache_data.clear()
    fake = fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/ShopEnsemble_App.py")
    at.run()

    assert not at.exception
    assert at.title[0].value == "📦 Browse Catalog"
    assert at.sidebar.success[0].value == "API connected"
    assert fake.list_products_call_count == 1
    assert fake.call_count == 0  # never calls POST /query
    assert any("2 of 2 products" in c.value for c in at.caption)


def test_catalog_page_category_filter_narrows_results(fake_client_factory):
    st.cache_data.clear()
    fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/ShopEnsemble_App.py")
    at.run()
    at.selectbox[0].select("laptop").run()

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)


def test_catalog_page_name_search_narrows_results(fake_client_factory):
    st.cache_data.clear()
    fake = fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/ShopEnsemble_App.py")
    at.run()
    at.text_input[0].set_value("Mobile").run()

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)
    assert fake.list_products_call_count == 1  # cached, not re-fetched on filter


def test_catalog_page_brand_filter_narrows_results(fake_client_factory):
    st.cache_data.clear()
    fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/ShopEnsemble_App.py")
    at.run()
    at.selectbox[1].select("ByteWorks").run()  # selectbox[0] is Category

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)


def test_catalog_page_price_range_filter_narrows_results(fake_client_factory):
    st.cache_data.clear()
    fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/ShopEnsemble_App.py")
    at.run()
    # Slider bounds come from the real fetched data (588.48-999.99 here) -
    # an out-of-bounds range is silently clamped/ignored by Streamlit, not
    # an error, so this must stay within [min_catalog_price, max_catalog_price].
    at.slider[0].set_range(588.48, 700.0).run()  # excludes LP0002 at $999.99

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)


def test_catalog_page_minimum_rating_filter_narrows_results(fake_client_factory):
    st.cache_data.clear()
    fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/ShopEnsemble_App.py")
    at.run()
    at.slider[1].set_value(4.5).run()  # excludes SP0001 at rating 4.0

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)


def test_catalog_page_shows_a_friendly_error_on_api_failure(fake_client_factory):
    st.cache_data.clear()
    fake_client_factory(products_error="Can't reach the ShopEnsemble API at http://localhost:8000.")

    at = _app_test("app/ui/ShopEnsemble_App.py")
    at.run()

    assert not at.exception
    assert "Can't reach the ShopEnsemble API" in at.error[0].value


def test_chat_assistant_page_sends_the_typed_query_and_renders_the_response(fake_client_factory):
    fake = fake_client_factory(query_response={"message": "I don't have a specialized agent for that yet."})

    at = _app_test("app/ui/pages/5_💬_Chat_Assistant.py")
    at.run()
    at.chat_input[0].set_value("do you sell groceries?").run()

    assert not at.exception
    assert fake.last_query == "do you sell groceries?"
    # Phase 7: fallback messages render as an informational box, not a warning.
    assert at.info[0].value == "I don't have a specialized agent for that yet."


def test_chat_assistant_page_shows_a_friendly_error_on_api_failure(fake_client_factory):
    fake_client_factory(query_error="Can't reach the ShopEnsemble API at http://localhost:8000.")

    at = _app_test("app/ui/pages/5_💬_Chat_Assistant.py")
    at.run()
    at.chat_input[0].set_value("anything").run()

    assert not at.exception
    assert "Can't reach the ShopEnsemble API" in at.error[0].value


def test_chat_assistant_sends_the_same_32_hex_session_id_on_every_message(fake_client_factory):
    # Phase 5 spec B8: one session_id per browser session, generated once, so
    # the server can remember the conversation across turns.
    fake = fake_client_factory(query_response={"message": "ok"})

    at = _app_test("app/ui/pages/5_💬_Chat_Assistant.py")
    at.run()
    at.chat_input[0].set_value("first").run()
    at.chat_input[0].set_value("second").run()

    assert not at.exception
    first, second = fake.session_ids_seen
    assert first == second
    assert len(first) == 32 and all(c in "0123456789abcdef" for c in first)


def test_form_pages_send_no_session_id(fake_client_factory):
    # The four form-based pages take explicit inputs by design — no hidden memory.
    fake = fake_client_factory(query_response={"products": [], "rationale": "Nothing matched."})

    at = _app_test("app/ui/pages/1_🎯_Recommendations.py")
    at.run()
    at.button[0].click().run()

    assert fake.call_count >= 1
    assert set(fake.session_ids_seen) == {None}


def test_new_chat_clears_the_transcript_rotates_the_session_and_deletes_the_old_one(fake_client_factory):
    fake = fake_client_factory(query_response={"message": "ok"})

    at = _app_test("app/ui/pages/5_💬_Chat_Assistant.py")
    at.run()
    at.chat_input[0].set_value("hello").run()
    old_session_id = fake.last_session_id
    assert len(at.session_state["messages"]) == 2  # the user turn + the assistant reply

    new_chat = next(button for button in at.sidebar.button if "New chat" in button.label)
    new_chat.click().run()

    assert not at.exception
    assert at.session_state["messages"] == []
    assert fake.deleted_session_ids == [old_session_id]  # the OLD id was cleared server-side
    at.chat_input[0].set_value("after reset").run()
    assert fake.last_session_id != old_session_id  # and a fresh id is used from now on


def test_new_chat_does_not_break_the_page_when_the_delete_call_fails(monkeypatch):
    # Real client (so the real best-effort swallowing is exercised) over a
    # transport whose DELETE returns 500 — the page must still reset cleanly.
    import httpx

    from app.ui import client as client_module

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return httpx.Response(200, json={"message": "ok"})

    real = client_module.ShopEnsembleAPIClient(base_url="http://testserver", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client_module, "get_client", lambda: real)

    at = _app_test("app/ui/pages/5_💬_Chat_Assistant.py")
    at.run()
    at.chat_input[0].set_value("hello").run()
    next(button for button in at.sidebar.button if "New chat" in button.label).click().run()

    assert not at.exception
    assert at.session_state["messages"] == []


def test_recommendations_page_composes_the_expected_query(fake_client_factory):
    fake = fake_client_factory(query_response={"products": [], "rationale": "Nothing matched."})

    at = _app_test("app/ui/pages/1_🎯_Recommendations.py")
    at.run()
    at.selectbox[0].select("laptop").run()
    at.number_input[0].set_value(700).run()
    at.button[0].click().run()

    assert not at.exception
    assert fake.last_query == "Recommend a laptop under $700."
    assert at.info[0].value == "No products matched."


def test_compare_page_requires_at_least_two_ids(fake_client_factory):
    fake = fake_client_factory()

    at = _app_test("app/ui/pages/2_⚖️_Compare_Products.py")
    at.run()
    at.text_input[0].set_value("SP0001").run()
    at.button[0].click().run()

    assert not at.exception
    assert fake.call_count == 0
    assert "at least 2" in at.warning[0].value


def test_compare_page_composes_the_expected_query(fake_client_factory):
    fake = fake_client_factory(query_response={"products": [], "differences": ["a", "b"]})

    at = _app_test("app/ui/pages/2_⚖️_Compare_Products.py")
    at.run()
    at.text_input[0].set_value("SP0001, SP0004").run()
    at.button[0].click().run()

    assert not at.exception
    assert fake.last_query == "Compare SP0001 and SP0004."


def test_review_summaries_page_composes_the_expected_query(fake_client_factory):
    fake = fake_client_factory(
        query_response={"product_id": "SP0001", "summary": "Good.", "sentiment": "positive", "review_count": 2}
    )

    at = _app_test("app/ui/pages/3_⭐_Review_Summaries.py")
    at.run()
    at.text_input[0].set_value("SP0001").run()
    at.button[0].click().run()

    assert not at.exception
    assert fake.last_query == "What do people say about SP0001?"


def test_policy_faq_page_composes_the_expected_query_with_a_policy_type(fake_client_factory):
    fake = fake_client_factory(query_response={"policy": None, "answer": "..."})

    at = _app_test("app/ui/pages/4_📋_Policy_FAQ.py")
    at.run()
    at.selectbox[0].select("returns").run()
    at.text_area[0].set_value("laptops?").run()
    at.button[0].click().run()

    assert not at.exception
    assert fake.last_query == "[returns] laptops?"
