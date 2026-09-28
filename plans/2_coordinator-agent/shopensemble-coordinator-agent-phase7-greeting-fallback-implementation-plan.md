# Phase 7 — Greeting & Fallback Wording Implementation Plan

**Status:** ✅ Implemented and verified (2026-09-27). 273 fast + 11 integration + 14 eval tests; routing accuracy unchanged at 100% (42/42). See Implementation Notes below.
**Governing spec:** [shopensemble-coordinator-agent-phase7-greeting-fallback-spec.md](../../specs/2_coordinator-agent/shopensemble-coordinator-agent-phase7-greeting-fallback-spec.md).
**Baseline before starting:** fast 261 passed, integration 11 passed, eval 13 passed (Phase 6).

## Implementation Notes (added post-implementation)

- **3 small corrections found by the tests themselves, all in the greeting detector, logged here since the spec's Decision Log is already closed:**
  1. `_GREETING_TRIGGERS` was too narrow — "good morning"/"Good Evening!" have no bare "hi"/"hello", so `morning`/`afternoon`/`evening`/`whats` were added as triggers in their own right.
  2. `"what's up"` tokenized to `["what", "s", "up"]` (the apostrophe split the word) — fixed by stripping apostrophes before tokenizing, so it reads as `"whats"`, matching the vocabulary.
  3. A pre-existing Phase 5 regression test used `"hello there"` to check prompt sanitization byte-for-byte — that phrase is now correctly caught as a pure greeting, so the test's example message was swapped to a non-greeting phrase (`"what is your policy"`); its actual purpose (prompt sanitization) is unaffected.
- **Two other pre-existing tests asserted `st.warning` for a fallback-shaped response** (`tests/ui/test_pages.py`, one in the Chat Assistant page) — updated to `st.info` alongside the Phase 7 rendering change; both are cosmetic-assertion updates, not behavior changes beyond what the spec calls for.
- **Lint scoped correctly this time**: the exact touched-file list was named explicitly (learned from the Phase 6 process mistake), and `git diff --stat` was checked before finishing — no unrelated file was touched.
- **Not committed** as part of this task's own execution — committed together with the git check-in the user requested in the same turn.

## Task 1 — Shared capability blurb + 3 messages

Tests (`tests/agents/test_coordinator.py`): the greeting reply, low-confidence fallback, and confident-none message each contain the shared capability phrase; the three are distinct strings (different openers).
Implement (`app/agents/coordinator.py`): `ASSISTANT_CAPABILITIES_BLURB` constant; `GREETING_REPLY`, `FALLBACK_MESSAGE` (updated in place), and the confident-"none" message all built from it.

## Task 2 — Deterministic greeting detection

Tests: pure greetings ("hi", "HI how are you you", "hello", "good morning", "hey there", "what's up") → `GREETING_REPLY`, **zero** coordinator/model calls (proven via a bare `TestModel()` that would raise if actually invoked); "hi, do you have laptops under $500?" and any real product/policy query → classified normally, unaffected; empty/whitespace query → not a greeting (falls through to existing sanitize/validation behavior).
Implement: `_GREETING_VOCABULARY`, `_GREETING_TRIGGERS` (module constants), `_is_pure_greeting(query) -> bool`; in `handle_turn`, checked immediately after `sanitize_query`, before building the prompt or calling the coordinator — returns `TurnResult(FallbackResponse(message=GREETING_REPLY), TurnFacts(tool="fallback"))` directly.

## Task 3 — UI rendering

Test (`tests/ui/test_components.py`): a fallback-shaped response renders via `st.info`, not `st.warning`.
Implement (`app/ui/components.py::_render_fallback`): swap the call.

## Task 4 — Eval + real end-to-end
Add one golden case (real API): "HI how are you you" → response contains "ShopEnsemble" and offers help, with the routing/model call count unaffected by this addition (a code-level check, not an LLM assertion, since the deterministic path makes no model call to evaluate). Run fast + integration + eval once; lint the exact touched files (explicit list, not a timestamp glob — see Phase 6's process-mistake note); restart the live app and verify the reported message live, plus a mixed "hi, recommend a laptop" case still classifies normally.

---

**Version**: 2.0 (implemented)
**Last Updated**: 2026-09-27
