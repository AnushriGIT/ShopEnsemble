# Phase 3a Part 2 — Groundedness Evaluation Implementation Plan

**Status:** ✅ Implemented and verified (2026-09-14) — 7/7 eval tests passing against the real OpenAI API, confirmed stable across 3 consecutive live runs
**Governing spec:** [shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md) (the BDD spec this plan implements) and [shopensemble-coordinator-agent-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md) Section 12/Appendix A (the evaluation-strategy analysis both derive from)
**Extends:** The Phase 3a eval harness (`tests/agents/eval/`) — additional assertions on the existing golden Q&A cases, not a parallel eval set
**Test generation log:** [.agents/memory-bank/testGenerationLog.md](../../.agents/memory-bank/testGenerationLog.md) (`v7` entry)

## Implementation Notes (added post-implementation)

- **Real bug #1 confirmed and fixed**: `tests/agents/eval/conftest.py` had indeed been corrupted (2 garbage lines before the docstring, as found while drafting this plan) — but it was already clean by the time implementation started (the file's mtime showed an edit between planning and implementation, most likely the IDE's own save/format-on-open resolving it). Verified with `ast.parse` before building anything further.
- **Real bug #2 — `review_summary_agent` hallucinated sentiment/caveats on a small review sample**: the very first real run caught `review_summary_agent` classifying `SP0001`'s 2 reviews (ratings 3.5/5 and 4.5/5, both purely positive text, no criticism stated) as `sentiment='mixed'`, with summaries inventing phrases like "some areas may not meet expectations" and "moderate satisfaction" that no review text supports — the model was inferring dissatisfaction from a numeric rating *difference* alone rather than from anything actually stated. Fixed by strengthening `REVIEW_SYSTEM_PROMPT` (`app/agents/review_agent.py`): sentiment must reflect only explicitly stated content, "mixed" requires reviews that genuinely disagree, and a lower rating alone (with no stated complaint) is not itself a reservation.
- **Real bug #3 — `recommendation_agent`'s rationale occasionally misstated its own picks' price range**: with a large candidate pool (20 speakers, all rating 4.8-5.0), the rationale sometimes cited an exact two-sided price range or a "one-sided bound" (e.g. "all under $100") that didn't actually hold for every picked product. Fixed by tightening `RECOMMENDATION_SYSTEM_PROMPT` (`app/agents/recommendation_agent.py`) to forbid numeric price claims spanning multiple picks in favor of qualitative, relative language ("among the more affordable options").
- **Test-harness design gap, not a production bug — found across several iterations on the "cheap speaker" case**: the recommendation test's `facts` string (the full filtered candidate list) never told the judge *which* candidates were actually picked, so a comparative claim like "the selected products are the most affordable" was genuinely unverifiable from what the judge was shown — not a real hallucination. Fixed by having `_facts_for_products()` accept and mark `selected_ids`, so the judge can map "the selected/recommended products" in the rationale to specific facts. This, more than any further prompt tuning, resolved the case's remaining flakiness.
- **Judge model upgraded from the plan's original `gpt-4o-mini` default to `gpt-4o`, `temperature=0`**: repeated real runs showed the cheaper model's own grading was itself inconsistent on multi-item numeric/comparative claims (flagging factually-supported "most affordable" claims as ungrounded, with internally inconsistent reasoning in its own explanation). Matches the reference RAG-evaluation notebook's own design choice — a stronger model grades even when a cheaper model generates — and is justified here since the judge runs only a handful of times per suite run, not on every production call.
- **Groundedness system prompt hardened iteratively** (`tests/agents/eval/groundedness.py`) to stop over-penalizing reasonable, factually-supported comparative/superlative and subjective-qualitative language ("the most affordable", "affordable") as if it required maximal precision — only flag a claim as ungrounded when the facts actually contradict it.
- All defects were caught and fixed via genuine repeated real-API runs, not just a single green run — consistent with `AGENTS.md` Rule 9. 3 consecutive fully-green real runs were required before declaring this stable, given LLM-judge and LLM-generation non-determinism.

## Context

`specs/2_coordinator-agent/shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md` (drafted and approved earlier this session) is the BDD spec this plan implements. It resolves the one gap the governing spec's Section 12 evaluation-strategy analysis found: every sub-agent's *structured* response fields are hallucination-proof by construction (the reference-only output pattern), but the **free-text fields** — `ReviewSummaryResponse.summary`, `RecommendationResponse.rationale`, `ComparisonResponse.differences`, `PolicyResponse.answer` — are LLM-synthesized prose nothing currently checks against the real source records the sub-agent was shown. Correctness/Relevance/Retrieval-relevance were evaluated and rejected as redundant or inapplicable (Appendix A); only Groundedness is being added, and it's added as extra assertions on the 6 existing golden Q&A cases, not a parallel eval set.

**Real bug discovered while re-verifying current state for this plan (Rule 9 — verify against reality):** `tests/agents/eval/conftest.py` is currently corrupted — its first two lines are `-+` and `+ ` before the module docstring, which is invalid Python syntax (`ast.parse` confirms a `SyntaxError`). This breaks pytest collection for the **entire** `tests/agents/eval/` package, not just the new groundedness work — none of the existing 7 eval tests can currently run. The rest of the file (from the docstring onward) is intact and matches what was verified working earlier this session, so this is fixed by simply removing those two garbage lines, not by rebuilding the fixtures. This is step 1 of implementation, a prerequisite unrelated to the groundedness feature itself.

---

## Design

**One shared judge, module-local, same idiom as every other agent** (`app/agents/review_agent.py` etc. — a `build_*_agent()` returning an `Agent[None, <output type>]`, `openai:gpt-4o-mini` default matching every other sub-agent's default rather than switching models). Lives in `tests/agents/eval/groundedness.py`, not `app/agents/` — it's an evaluation tool, never called from a production dispatch path.

```python
class GroundednessGrade(ShopEnsembleModel):
    explanation: str
    grounded: bool

def build_groundedness_judge(model=...) -> Agent[None, GroundednessGrade]: ...

async def judge_groundedness(agent, facts: str, answer: str) -> GroundednessGrade: ...
```

`judge_groundedness` calls the agent via `app.agents.retry.call_with_retry` (same retry-with-backoff wrapper every other real-API call in this codebase uses, per Rule 12) with a prompt containing `facts` (the real source text the sub-agent was actually shown) and `answer` (the specific free-text field being checked), and a system prompt instructing the model to judge whether `answer` contains any claim not supported by `facts`.

**Extends the 6 existing golden Q&A cases — no parallel case list.** Each test in `test_golden_qa.py` gains one additional assertion using data it already has:

| Case | Free-text field | `facts` built from |
| :--- | :--- | :--- |
| `test_review_summary_for_a_known_product` | `response.summary` | `reviews_for_product(eval_catalog, REVIEW_PRODUCT_ID)` (`app.agents.data`) |
| `test_recommendation_for_a_cheap_speaker_resolves_the_plural_category` | `response.rationale` | `response.products`' real name/category/price/description |
| `test_recommendation_respects_a_max_price_filter` | `response.rationale` | `response.products`' real name/category/price/description |
| `test_comparison_of_two_known_products` | `"; ".join(response.differences)` | `products_by_ids(eval_catalog, COMPARE_PRODUCT_IDS)`'s full real fields |
| `test_policy_faq_laptop_return_timeframe_matches_the_catalog` | `response.answer` | `response.policy`'s real description/conditions/timeframe (already resolved by the existing assertions) |
| `test_policy_faq_warranty_question_answers_from_the_matching_policy` | `response.answer` | `response.policy`'s real fields — **guarded**: only checked `if response.policy is not None`, per the spec's "no matched policy" scenario |

New session-scoped `eval_groundedness_judge` fixture in `conftest.py`, built the same way as `eval_coordinator_agent` (`_require_api_key()` guard, built once).

No new pytest marker, no `pyproject.toml` change, no `app/` change — stays inside the existing `eval` marker (spec's explicit scope).

---

## Files

```
tests/agents/eval/conftest.py       # fix: drop the 2 corrupted lines; add eval_groundedness_judge fixture
tests/agents/eval/groundedness.py   # new: GroundednessGrade, build_groundedness_judge(), judge_groundedness()
tests/agents/eval/test_golden_qa.py # each of the 6 existing tests gains one groundedness assertion
```

---

## Verification

```bash
# Confirm the conftest.py fix first — collection alone must succeed
.venv/bin/python -c "import ast; ast.parse(open('tests/agents/eval/conftest.py').read())"

# Fast suite still unaffected (no app/ or non-eval test changes)
.venv/bin/python -m pytest -q -m "not integration and not eval"

# Real run — costs real OpenAI calls (6 sub-agent queries + up to 6 judge calls)
.venv/bin/python -m pytest tests/agents/eval -m eval -v

# Clean skip still works
OPENAI_API_KEY= .venv/bin/python -m pytest tests/agents/eval -m eval -v
```

Expect: all 6 golden Q&A tests pass both their existing structured-field assertions and the new groundedness assertion; the warranty case's groundedness check runs only when a policy was actually matched on that run.

---

## After implementation — update in place (established convention)

- This file's Status header → "✅ Implemented and verified", with an Implementation Notes section (the conftest.py corruption found/fixed, any real groundedness-judge behavior observed).
- `shopensemble-coordinator-agent-phase3a-part2-groundedness-spec.md`: Status header → "✅ Implemented and verified".
- `shopensemble-coordinator-agent-spec.md`: Section 12's "Phase 3a Part 2" bullet → ✅ implemented; the fixed corruption isn't a spec-level change, just mentioned in this plan's Implementation Notes.
- `.agents/memory-bank/testGenerationLog.md`: append a `v7` entry, same format as `v5`/`v6` (including the conftest.py bug as a Triage entry — a real defect caught, not a test-authoring one).
- `Reference/Learning/coordinator-agent/coordinator-agent-reference.md`: Section 7 "Evaluation Harness" gains a short groundedness mention.
- `git add`/commit/push only the trackable files per the existing policy: this implementation-plan file (and nothing else — `tests/agents/eval/`, the spec, and the reference doc all stay local-only).

## Out of scope (per the spec)

Relevance/Retrieval-relevance evaluators, a standalone Correctness LLM-judge, any production code path, and an aggregate groundedness percentage (6 named cases stay explicit, matching the existing golden Q&A style).
