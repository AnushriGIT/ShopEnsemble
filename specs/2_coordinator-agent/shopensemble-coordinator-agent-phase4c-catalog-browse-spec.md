# Coordinator Agent — Phase 4c: Product Catalog Browsing Spec

**Status:** ✅ Implemented and verified (2026-09-17) — see the [implementation plan](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase4c-catalog-browse-implementation-plan.md)'s Implementation Notes.
**Governing spec:** [shopensemble-coordinator-agent-spec.md](shopensemble-coordinator-agent-spec.md) — no existing section covers this; it's a new capability, not a gap in an already-scoped one (see Context below). `specs/shopensemble-project-requirements.md` Section 7 "UI Requirements" lists the 5 required workflows this project was originally scoped to — catalog browsing is not among them.
**Extends:** Phase 4a (`app/ui/`, the Streamlit UI) — **replaces the conversational chat assistant as the app's home page** (clarified during planning, 2026-09-17 — see Design below); the chat assistant relocates into `app/ui/pages/` as a regular sidebar entry alongside the existing 4 form-based workflows. Also extends the API layer (`app/api/`) with one new route.
**Test generation log:** `.agents/memory-bank/testGenerationLog.md` (will land as `v14` once implemented).

**Why a separate file, not folded into an existing spec**: same reasoning as the groundedness spec (`shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md`) — `AGENTS.md` Rule 1 requires a BDD spec before any code, and Rule 10 keeps each domain's *living* spec/requirements doc as one file, updated in place rather than forked. This isn't an edit to an existing scoped requirement; it's a new one, discovered live in conversation rather than written down in advance — so it gets its own spec file first, exactly the process this project already uses for exactly this situation.

---

## Context / Narrative

Every one of the 5 originally-required UI workflows (`shopensemble-project-requirements.md` Section 7) assumes the user already knows *something specific* to ask about — a product ID to summarize reviews for, 2+ product IDs to compare, a category/price to recommend within, a policy type to ask about. None of them answer the more basic question: **"what products does this store even carry?"**

This gap surfaced directly in conversation, not from a written requirement — while walking through how to actually use the running app, it became clear there's no way to discover a valid product ID (`SP0001`, `LP0002`, ...) except by already having one from outside the app (the raw CSV, or a lucky guess). The catalog itself is not small — checked directly: **2,000 products** across 4 categories (`laptop`, `smartphone`, `smart_tv`, `speaker`).

This is additive, not a fix to broken behavior — every existing workflow still requires the caller to already know what they're asking about, by design (that's how the coordinator's classification works). This spec adds one new, independent way to explore the catalog *before* using any of those 5, not a replacement for any of them.

---

## Design

**One new API route — deliberately outside the LLM/coordinator path entirely.**

```python
@router.get("/products", response_model=list[Product])
async def products(app_state: AppState = Depends(get_app_state)) -> list[Product]:
    return app_state.catalog.products
```

Returns the full, existing `app.models.Product` list directly from `AppState.catalog` — no new response schema needed, reusing the model already used throughout `app/agents/`. **No coordinator call, no LLM, no cost.** Browsing "what exists" is a plain data read, not a classification-and-generation task; routing it through `handle_query()` would spend real OpenAI tokens/latency on something that needs neither — the same reasoning `/health` already stays outside that path. For the same reason, **no caching or rate-limiting** on this route either (matching `/health`'s scope, not `/query`'s) — it's cheap and deterministic enough not to need either.

**Catalog becomes the home page — clarified during planning (2026-09-17), supersedes this spec's original "6th page" framing.** `app/ui/streamlit_app.py` (currently the conversational chat assistant) becomes the catalog browse page; the chat assistant's existing content relocates, essentially unchanged, into a new `app/ui/pages/5_💬_Chat_Assistant.py` — same `session_state["messages"]` transcript logic (a process-wide key, unaffected by which file is the entry point), same `st.chat_input`/`st.chat_message` loop. This was a genuine fork settled with the user directly rather than assumed: an alternative ("Catalog is a new 6th page; chat assistant stays the home page") was offered and not chosen.

The catalog page itself, structured like the existing form-based pages:
- Fetch the full catalog once via the already-built `ShopEnsembleAPIClient.list_products()`, wrapped in `st.cache_data(ttl=...)` at the page level — the catalog doesn't change mid-session, so this avoids re-fetching 2,000 records on every rerun (every widget interaction reruns the whole script — see `Streamlit-Tutorial.md` §1/§3). Filtering happens *after* the cached fetch, on the already-loaded data, not by re-querying the API per filter change.
- A category filter (`st.selectbox`, "All" + the 4 real categories) and a name-search text box (`st.text_input`), applied as a cheap in-memory filter over the cached list.
- Rendered as a sortable, scrollable `st.dataframe` (id, name, brand, category, price, rating, stock, description) — chosen over the product-card grid (this file's earlier design question, already answered: "Category filter + searchable table") specifically because a 2,000-row card grid is far heavier to scroll than one table Streamlit already knows how to virtualize.
- Keeps the existing `st.set_page_config(...)` call and the sidebar health-check block — both stay tied to whichever file is the actual entry point, same as today.
- **Must keep the `sys.path` bootstrap block** already present (see `Reference/Learning/Streamlit-Tutorial.md`'s gotcha entry) — a real bug hit and fixed earlier this session. The new `pages/5_💬_Chat_Assistant.py` needs its own copy too (depth `parents[3]`, matching the other 4 page files), from the start rather than discovered again the same way.

**Explicitly ruled out during planning, not just left unmentioned**: per-row "Review Summary"/"Add to Compare" actions, `st.switch_page` cross-page navigation, any `session_state` prefill between the catalog and other pages, a running comparison cart. All were proposed as options during planning and explicitly declined ("not on the catalog... user will copy item and check in chat window or move to a specific page") — the catalog is filterable and read-only, nothing more. See Out of Scope below.

**Scaffolding written before this spec was approved, now covered by the approved implementation plan**: the `GET /products` route in `app/api/routes.py`, and `ShopEnsembleAPIClient.list_products()` in `app/ui/client.py` — both written just before this spec was drafted, both still unused/inert until the implementation plan is actually built.

---

## Scenarios (Gherkin)

```gherkin
Feature: Browse the product catalog without already knowing a product ID
  A user with no prior knowledge of what this store carries can discover
  real products — and find a product ID to use with the other 5 workflows
  — without going through the coordinator or spending any LLM call.

  Scenario: Viewing the full catalog
    Given the Browse Catalog page is opened with no filters applied
    When the page loads
    Then all 2,000 real catalog products are shown in a table with name, brand, category, price, rating, and stock

  Scenario: Filtering by category
    Given the full catalog is loaded
    When the user selects "smartphone" from the category filter
    Then only products with category "smartphone" remain in the table

  Scenario: Searching by product name
    Given the full catalog is loaded
    When the user types part of a product name into the search box
    Then only products whose name contains that text (case-insensitive) remain in the table

  Scenario: Browsing never calls the coordinator or the LLM
    Given the Browse Catalog page is opened and filtered
    When the page's requests are inspected
    Then no request to POST /query occurs, and no new llm_usage log line appears — only GET /products is called

  Scenario: The API is unreachable
    Given the FastAPI backend is not running or not reachable
    When the Browse Catalog page attempts to load the catalog
    Then a safe, non-crashing error message is shown (the existing ShopEnsembleAPIError pattern), not a raw exception

  Scenario: The catalog is the app's home page, and chat still works from its new location
    Given the app is opened fresh at its base URL (streamlit run app/ui/streamlit_app.py)
    When the page loads
    Then the catalog table is shown immediately, not the conversational chat assistant
    And the sidebar lists "Chat Assistant" alongside Recommendations, Compare Products, Review Summaries, and Policy FAQ
    And opening the Chat Assistant page still sends messages and renders responses exactly as it did before this change
```

---

## Files (per the approved implementation plan)

```
app/api/routes.py                    # GET /products route (already added)
app/ui/client.py                     # ShopEnsembleAPIClient.list_products() (already added)
app/ui/streamlit_app.py              # replaced: chat content -> catalog browse content
app/ui/pages/5_💬_Chat_Assistant.py  # new — relocated chat content
tests/api/test_products.py           # new — contract test for GET /products
tests/ui/conftest.py                 # FakeClient extended with list_products()
tests/ui/test_pages.py               # 2 chat tests retargeted, 1 adjusted, new catalog tests
```

No changes to `app/agents/` — this bypasses the coordinator entirely, by design.

---

## Verification (once implemented)

```bash
# Fast suite, no real API calls
.venv/bin/python -m pytest -q -m "not integration and not eval"

# Real manual verification
uvicorn app.api.main:app --reload --port 8123 &
streamlit run app/ui/streamlit_app.py --server.port 8501
# Open Browse Catalog, confirm all 2,000 real products render, filters work,
# and logs/api.log gains zero new llm_usage lines from this workflow —
# only /health and /query trigger those, /products should not.
```

---

## Out of scope

- **Per-row actions ("Review Summary"/"Add to Compare" buttons on each catalog row), `st.switch_page` navigation, `session_state` prefill between pages, a running comparison cart** — proposed during planning as concrete options and explicitly declined by the user ("not on the catalog... user will copy item and check in chat window or move to a specific page"). The catalog is filterable and read-only; discovering an ID here and using it elsewhere is a manual, deliberate user action, not an automated hand-off.
- **Pagination beyond `st.dataframe`'s own built-in virtualized scrolling** — not needed at 2,000 rows; revisit only if the catalog grows by an order of magnitude.
- ~~**Price-range filtering** — considered and not chosen initially~~ — **added 2026-09-17**, directly requested: price range (`st.slider`, bounds from the real fetched data), brand (`st.selectbox`, 15 real brands), and minimum rating (`st.slider`) all now filter the table alongside category and name search. No API change needed, as this section originally predicted (already client-side filtering over the cached `GET /products` result).
- **Product images** — the catalog has no image data (`app.models.Product` has no image field); out of scope for this or any future phase unless the underlying data model changes.
- **Editing/writing back to the catalog** — read-only, matching every other part of this project (no write path exists anywhere).
- **Authentication/access control on `/products`** — already out of scope project-wide (no auth exists on any route, including `/query`).

---

## Next step

Approved (2026-09-17) — implementation plan saved: [shopensemble-coordinator-agent-phase4c-catalog-browse-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase4c-catalog-browse-implementation-plan.md). Per this session's convention, plan approval alone means the plan is saved and nothing further is built until an explicit go-ahead — followed then by real end-to-end verification against the live API before this is considered done.

---

**Version**: 2.0 (revised post-approval: home-page swap, cross-page interactivity ruled out)
**Last Updated**: 2026-09-17
