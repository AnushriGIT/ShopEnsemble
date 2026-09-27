# Phase 4c — Product Catalog Browsing (Home Page Swap) Implementation Plan

**Status:** ✅ Implemented and verified (2026-09-17) — 159/159 in the full fast suite (up from 154), plus real end-to-end verification against a live `uvicorn` server and the real OpenAI API. See Implementation Notes below.
**Governing spec:** [shopensemble-coordinator-agent-phase4c-catalog-browse-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-phase4c-catalog-browse-spec.md)
**Test generation log:** [.agents/memory-bank/testGenerationLog.md](../../.agents/memory-bank/testGenerationLog.md) (`v14` entry)

## Implementation Notes (added post-implementation)

- **Built exactly as designed** — no architecture changes during implementation. Both findings below were test-authoring discoveries, not design flaws.
- **`st.cache_data` is a process-wide cache, not per-test.** The first draft of the 3 new catalog-filter tests failed/passed for the wrong reason — a prior test's cached `_load_products()` result was still being served to later tests in the same pytest process. Same category of bug as Phase 4b's `TTLCache` test-isolation issue, one layer up the stack. Fixed with `st.cache_data.clear()` at the start of every catalog test.
- **`at.caption[-1]` didn't index what it looked like it would.** Assumed the "N of M products" caption was the last one AppTest renders; it actually indexed the *sidebar's* caption instead — `at.caption` includes sidebar elements, not just main-area ones, and their position isn't simply "after everything else." Found by printing every `at.caption` entry with its index and looking at the real output (Rule 9), not by guessing. Fixed by searching all captions for the expected substring rather than relying on a fixed index.
- **Real end-to-end verification, both directions**: drove the actual `streamlit_app.py` catalog page via `AppTest` against a live `uvicorn` server (real OpenAI-backed process) — confirmed all 2,000 real products render, and `logs/api.log` gained **zero** new lines from browsing/filtering (proof no LLM call happens). Then drove the relocated `pages/5_💬_Chat_Assistant.py` against the same live server for a real query — confirmed it still works identically to before the move, producing 5 new log lines including a genuine `llm_usage` line.

## Context

Every one of the 5 originally-required UI workflows assumes the user already knows *something specific* to ask about (a product ID, a category, a policy type). There's no way to discover what the store even carries — checked directly: **2,000 products** across 4 categories (`laptop`, `smartphone`, `smart_tv`, `speaker`). This gap surfaced live in conversation, not from a written requirement, so per `AGENTS.md` Rule 1 a spec was written and approved first (see the governing spec above) before this plan.

Settled during planning, via direct questions to the user:
- **Catalog becomes the app's home page**, not an additional 6th page. The conversational chat assistant (currently `app/ui/streamlit_app.py`) moves into `pages/` as a regular sidebar entry, same tier as Recommendations/Compare/Reviews/Policy FAQ.
- **No cross-page interactivity** — explicitly ruled out ("not on the catalog... user will copy item and check in chat window or move to a specific page"). No per-row buttons, no `st.switch_page`, no `session_state` prefill, no comparison cart. The catalog is a filterable, read-only table — nothing more.
- Table shows item ID and description (explicit ask) plus the other catalog fields (name, brand, category, price, rating, stock).

Already-existing scaffolding (built before this plan, unused until now): `GET /products` route in `app/api/routes.py` (no LLM call, no cache/rate-limit — same class as `/health`), `ShopEnsembleAPIClient.list_products()` in `app/ui/client.py`.

## Design

**1. `app/ui/streamlit_app.py` becomes the catalog browse page** (its current chat content moves to #2). New content:
- Keeps the existing `st.set_page_config(...)` and sidebar health-check block (site-wide identity/status — lives wherever the actual entry point is).
- Keeps the sys.path bootstrap block already present (same depth, `parents[2]` — this file's location doesn't change).
- Fetch via `st.cache_data(ttl=300)` wrapping `get_client().list_products()` — fetched once, not re-fetched on every filter interaction.
- A category `st.selectbox` ("All" + the 4 real categories) and a name `st.text_input` search box, both applied as an in-memory filter over the cached list — no new API calls per filter change.
- Rendered via `st.dataframe` (id, name, brand, category, price, rating, stock, description) — handles 2,000 rows natively via virtualized scrolling, no pagination needed.

**2. New `app/ui/pages/5_💬_Chat_Assistant.py`** — the current `streamlit_app.py` chat content, relocated essentially unchanged: same `session_state.setdefault("messages", [])` transcript logic (process-wide `session_state`, unaffected by which file is the entry point), same `st.chat_input`/`st.chat_message` loop. Own sys.path bootstrap at `parents[3]` depth, matching the other 4 files already under `pages/`. Does **not** duplicate the sidebar health-check block — matches the existing convention that only the entry-point file shows it.

**3. `FakeClient` (`tests/ui/conftest.py`) gains `list_products()` support** — extend the constructor with `products_response`/`products_error` params and a `list_products()` method mirroring the existing `query()` pattern, plus a call-count counter so a test can assert the catalog page never triggers `POST /query`.

**4. `tests/ui/test_pages.py` updates**:
- The 2 existing chat-interaction tests (`test_main_app_chat_sends_the_typed_query...`, `test_main_app_chat_shows_a_friendly_error...`) retarget from `"app/ui/streamlit_app.py"` to `"app/ui/pages/5_💬_Chat_Assistant.py"` — same assertions, new path.
- `test_main_app_loads_and_shows_health_status` stays pointed at `streamlit_app.py` (still the entry point) but now exercises catalog content.
- New tests: catalog page loads and shows all 2,000 rows unfiltered; category filter narrows results; name search narrows results; no `POST /query` call happens on load or on filtering.

**5. New `tests/api/test_products.py`** — contract test(s) for `GET /products`: returns the full catalog, matches `Product` schema, no auth/cache/rate-limit headers expected.

## Files

```
app/ui/streamlit_app.py                # replaced: chat content -> catalog browse content
app/ui/pages/5_💬_Chat_Assistant.py     # new: relocated chat content
app/ui/client.py                       # list_products() already exists, no change needed
app/api/routes.py                      # GET /products already exists, no change needed
tests/ui/conftest.py                   # FakeClient extended with list_products()
tests/ui/test_pages.py                 # 2 tests retargeted, 1 adjusted, ~3-4 new tests
tests/api/test_products.py             # new
```

## Verification

```bash
# Fast suite, no real API calls
.venv/bin/python -m pytest -q -m "not integration and not eval"

# Real manual check
uvicorn app.api.main:app --reload --port 8123 &
SHOPENSEMBLE_API_BASE_URL=http://localhost:8123 streamlit run app/ui/streamlit_app.py --server.port 8501
# Confirm: opening localhost:8501 shows the catalog table (not chat) with all
# 2,000 real products; category filter and search both narrow results; the
# sidebar lists Chat Assistant + the 4 existing workflows; logs/api.log
# gains zero new llm_usage lines from browsing/filtering (only /products
# hits) — chat still works normally from its new sidebar page.
```

## After implementation — update in place (established convention)

- `Reference/Learning/coordinator-agent/coordinator-agent-reference.md` — module table, page/workflow list, home-page note.
- `Reference/Learning/coordinator-agent/INDEX.md` — if it lists page structure.
- `.agents/memory-bank/testGenerationLog.md` — new `v14` entry.
- `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md` — Section 13 roadmap row + Appendix A decision log (home-page-swap decision, "no cross-page interactivity, explicitly declined" note).
- `git add`/commit/push: `app/ui/streamlit_app.py`, `app/ui/pages/5_💬_Chat_Assistant.py`, `tests/ui/*` — all inside the already-tracked `app/ui/`/`tests/ui/` scope. `app/api/routes.py`, `app/ui/client.py`, `tests/api/test_products.py` stay local-only (already-excluded directories), same as every other Phase 4b/4c backend file.

## Out of scope

Per-row "Review Summary"/"Add to Compare" buttons, `st.switch_page` navigation, `session_state` prefill between pages, a comparison cart — explicitly declined by the user during planning. Pagination beyond `st.dataframe`'s built-in virtualization. Price-range filtering, product images, catalog editing, auth on `/products`.

---

**Version**: 1.0
**Last Updated**: 2026-09-17
