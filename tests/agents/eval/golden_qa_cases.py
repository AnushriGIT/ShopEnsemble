"""Shared real-catalog constants for the golden Q&A eval set.

Values are drawn straight from ``data/products.csv`` / ``data/store_policies.csv``
so ``test_golden_qa.py`` can assert against real ground truth, not just "some
answer came back". Keep this in sync if the source CSVs change.
"""

# review_summary_agent
REVIEW_PRODUCT_ID = "SP0001"  # smartphone, has reviews in data/reviews.csv

# recommendation_agent
RECOMMEND_CATEGORY_QUERY = "recommend a cheap speaker"  # known-bug regression (plural -> singular)
RECOMMEND_SPEAKER_CATEGORY = "speaker"
RECOMMEND_LAPTOP_MAX_PRICE_QUERY = "recommend a laptop under $700"

# comparison_agent
COMPARE_PRODUCT_IDS = ["SP0001", "SP0004"]  # both smartphones
COMPARE_QUERY = "compare SP0001 and SP0004"

# policy_faq_agent
POLICY_LAPTOP_RETURN_QUERY = "what's your return policy for laptops?"  # known-bug regression
POLICY_LAPTOP_RETURN_TIMEFRAME_DAYS = 14  # data/store_policies.csv "Laptop Return Policy" row
POLICY_WARRANTY_QUERY = "what's covered under the smartphone warranty?"
POLICY_TYPE_WARRANTY = "warranty"
