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

    at = _app_test("app/ui/streamlit_app.py")
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

    at = _app_test("app/ui/streamlit_app.py")
    at.run()
    at.selectbox[0].select("laptop").run()

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)


def test_catalog_page_name_search_narrows_results(fake_client_factory):
    st.cache_data.clear()
    fake = fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/streamlit_app.py")
    at.run()
    at.text_input[0].set_value("Mobile").run()

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)
    assert fake.list_products_call_count == 1  # cached, not re-fetched on filter


def test_catalog_page_brand_filter_narrows_results(fake_client_factory):
    st.cache_data.clear()
    fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/streamlit_app.py")
    at.run()
    at.selectbox[1].select("ByteWorks").run()  # selectbox[0] is Category

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)


def test_catalog_page_price_range_filter_narrows_results(fake_client_factory):
    st.cache_data.clear()
    fake_client_factory(products_response=_SAMPLE_PRODUCTS)

    at = _app_test("app/ui/streamlit_app.py")
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

    at = _app_test("app/ui/streamlit_app.py")
    at.run()
    at.slider[1].set_value(4.5).run()  # excludes SP0001 at rating 4.0

    assert not at.exception
    assert any("1 of 2 products" in c.value for c in at.caption)


def test_catalog_page_shows_a_friendly_error_on_api_failure(fake_client_factory):
    st.cache_data.clear()
    fake_client_factory(products_error="Can't reach the ShopEnsemble API at http://localhost:8000.")

    at = _app_test("app/ui/streamlit_app.py")
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
    assert at.warning[0].value == "I don't have a specialized agent for that yet."


def test_chat_assistant_page_shows_a_friendly_error_on_api_failure(fake_client_factory):
    fake_client_factory(query_error="Can't reach the ShopEnsemble API at http://localhost:8000.")

    at = _app_test("app/ui/pages/5_💬_Chat_Assistant.py")
    at.run()
    at.chat_input[0].set_value("anything").run()

    assert not at.exception
    assert "Can't reach the ShopEnsemble API" in at.error[0].value


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
