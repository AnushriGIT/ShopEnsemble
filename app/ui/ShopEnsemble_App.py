"""Entry point + the "browse catalog" home page.

Run with the FastAPI backend already up:

    uvicorn app.api.main:app --reload
    streamlit run app/ui/ShopEnsemble_App.py

Phase 4c implementation plan: this used to be the conversational chat
assistant — that workflow moved, essentially unchanged, to
``app/ui/pages/5_💬_Chat_Assistant.py``. Every one of the other required
workflows (recommendations, comparison, review summaries, policy/FAQ, and
now chat) assumes the user already knows something specific to ask about
(a product ID, a category, a policy type); this page is the one place with
no such assumption — a plain, filterable view of the real catalog, so a
user with no prior knowledge can find something to ask the other pages
about. Read-only, no LLM/coordinator call anywhere on this page (GET
/products is a plain data read, same class as GET /health).
"""

import sys
from pathlib import Path

# `streamlit run app/ui/ShopEnsemble_App.py` only ever adds this script's own
# directory (app/ui/) to sys.path — never the project root — regardless of
# which directory the command is launched from (verified against the
# installed streamlit package's own web/bootstrap.py::_fix_sys_path).
# Without this, `from app.ui.client import ...` below raises
# ModuleNotFoundError: No module named 'app'. Every other entry point in
# this project (app/agents/cli.py, app/api/main.py) is instead run via
# `python -m ...`, which puts the project root on sys.path for free — this
# is the one entry point `streamlit run` invokes directly, so it needs its
# own fix. Applied identically in every app/ui/pages/*.py file too, since
# each is independently executable by Streamlit's multipage navigation.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.ui.client import ShopEnsembleAPIError, get_client

st.set_page_config(page_title="ShopEnsemble Assistant", page_icon="🛍️", layout="wide")

with st.sidebar:
    st.subheader("🛍️ ShopEnsemble")
    st.caption("Browse the catalog, then dig into a product on any of the other pages")
    try:
        get_client().health()
        st.success("API connected")
    except ShopEnsembleAPIError as error:
        st.error(str(error))

st.title("📦 Browse Catalog")
st.caption(
    "Not sure what to ask about? Find a product ID or name here, then use it on "
    "Review Summaries, Compare Products, Recommendations, or Chat Assistant."
)


@st.cache_data(ttl=300)
def _load_products() -> list[dict]:
    return get_client().list_products()


try:
    products = _load_products()
except ShopEnsembleAPIError as error:
    st.error(str(error))
else:
    categories = ["All"] + sorted({product["category"] for product in products})
    brands = ["All"] + sorted({product["brand"] for product in products})
    prices = [float(product["price"]) for product in products]
    min_catalog_price, max_catalog_price = min(prices), max(prices)

    row1_col1, row1_col2, row1_col3 = st.columns(3)
    with row1_col1:
        category = st.selectbox("Category", categories)
    with row1_col2:
        brand = st.selectbox("Brand", brands)
    with row1_col3:
        search = st.text_input("Search by name", placeholder="e.g. Mobile")

    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        # Bounds come from the real catalog data just fetched above, not a
        # hardcoded guess — stays correct if the underlying prices change.
        price_range = st.slider(
            "Price range ($)",
            min_value=min_catalog_price,
            max_value=max_catalog_price,
            value=(min_catalog_price, max_catalog_price),
        )
    with row2_col2:
        min_rating = st.slider("Minimum rating", min_value=0.0, max_value=5.0, value=0.0, step=0.5)

    filtered = [
        product
        for product in products
        if (category == "All" or product["category"] == category)
        and (brand == "All" or product["brand"] == brand)
        and (search.lower() in product["name"].lower() if search else True)
        and (price_range[0] <= float(product["price"]) <= price_range[1])
        and (float(product["rating"]) >= min_rating)
    ]

    st.caption(f"{len(filtered)} of {len(products)} products")
    st.dataframe(
        filtered,
        column_order=["id", "name", "brand", "category", "price", "rating", "stock", "description"],
        hide_index=True,
        width="stretch",
    )
