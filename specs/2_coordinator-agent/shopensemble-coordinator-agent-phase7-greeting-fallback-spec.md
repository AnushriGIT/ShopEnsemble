# Coordinator Agent — Phase 7: Greeting & Fallback Wording Spec

**Status:** ✅ Implemented and verified (2026-09-27) — 273 fast + 11 integration + 14 eval tests; routing accuracy unchanged at 100% (42/42); the reported greeting, a mixed greeting+request, and a generic out-of-scope query all verified live against the real OpenAI API.
**Governing spec:** [shopensemble-coordinator-agent-spec.md](shopensemble-coordinator-agent-spec.md).
**Implementation plan:** [shopensemble-coordinator-agent-phase7-greeting-fallback-implementation-plan.md](../../plans/2_coordinator-agent/shopensemble-coordinator-agent-phase7-greeting-fallback-implementation-plan.md).

---

## Context / Narrative

Reported from live use: "HI how are you you" returned "I'm not sure how to help with that." — the same terse line every other out-of-scope query gets (a joke request, "cancel my order", genuine nonsense). A greeting is not a failure the way those are; treating it identically reads as the assistant being broken rather than simply not doing small talk, and it wastes a classification call and its cost on a message with only one sensible reply.

### Goals
1. A plain greeting ("hi", "hello", "hey", "good morning", "how are you", "what's up", or combinations) gets a warm, on-brand reply that also tells the customer what the assistant can actually do — computed in code, with **no LLM call**, so it's free, instant, and never wrong.
2. Every other "couldn't help" case (low-confidence fallback, and a confident "none") states what the assistant *can* do instead of only what it can't — one shared line, so the two messages stay consistent and a future wording change is made once.
3. Zero effect on real product/policy queries: the greeting detector must not fire on a message that also asks something real ("hi, do you have laptops under $500").

## Design

**Deterministic detection, before the coordinator ever runs.** A query is a "pure greeting" if every word in it (lowercased, punctuation stripped) belongs to a small, fixed vocabulary of greeting/pleasantry words (`hi`, `hello`, `hey`, `howdy`, `greetings`, `yo`, `good`, `morning`, `afternoon`, `evening`, `how`, `are`, `you`, `youre`, `doing`, `going`, `whats`, `up`, `there`) **and** at least one word is an actual greeting trigger (`hi`/`hello`/`hey`/`howdy`/`greetings`/`yo`). This is checked in `handle_turn`, immediately after sanitizing the query and before the coordinator's classification call — same "deterministic first when there's one right answer" precedent as Phase 6's price/rating superlatives. Any message containing a word outside that vocabulary (a product name, a number, "laptop", "policy", ...) is **not** a pure greeting and goes through classification exactly as today; the check runs regardless of whether a session/context is active, since it depends only on the current message's text.

**One shared capability line, three openers.** A single constant states what the assistant can do; the greeting reply, the low-confidence fallback, and the confident-"none" fallback each prepend a different, appropriately-toned opener to it, so all three stay consistent by construction:
- Greeting → "Hi! I'm the ShopEnsemble shopping assistant — I can help you find products, compare them, check reviews, or answer store policy questions. What are you looking for today?"
- Low-confidence fallback → "I'm not able to help with that, but I can find products, compare them, check reviews, or answer store policy questions."
- Confident "none" → "I don't have a way to help with that specific request, but I can find products, compare them, check reviews, or answer store policy questions."

**Rendering.** Both fallback messages currently render as a `st.warning` (a yellow, alarm-toned box) in `app/ui/components.py`. Now that both state a positive next step rather than only an apology, they render as `st.info` (a neutral blue box) instead — a small, deliberate visual change, not incidental: a greeting reply must not look like a warning.

**Memory.** A greeting turn records `TurnFacts(tool="fallback")`, the same as today's fallback path — nothing about a greeting is worth remembering for a follow-up.

### Explicitly rejected
**Routing greetings through the model with a friendlier prompt.** A greeting has exactly one sensible reply; there's no reason to spend a call and accept any variance on it, matching the reasoning already recorded for Phase 6's deterministic superlatives.

---

## Scenarios (Gherkin)

```gherkin
Feature: A plain greeting gets a warm, useful reply with no LLM call
  Scenario: A bare greeting
    When the customer says "HI how are you you"
    Then the response introduces the ShopEnsemble assistant and what it can do
    And no coordinator/LLM call is made

  Scenario: A greeting combined with a real request is NOT short-circuited
    When the customer says "hi, do you have laptops under $500?"
    Then the request is classified and routed normally (recommendation_agent)

  Scenario: Genuine out-of-scope requests get a helpful, not just apologetic, message
    When the customer asks "tell me a joke"
    Then the response states what the assistant can do, not only that it can't help

  Scenario: The fallback no longer looks like a warning
    When any fallback response is shown
    Then it renders in a neutral, informational style, not an alarm style
```

---

## Files
```
app/agents/coordinator.py   # greeting detection + capability blurb constants + dispatch
app/ui/components.py        # _render_fallback: st.warning -> st.info
tests/agents/test_coordinator.py — extended
tests/ui/test_components.py — extended
skills/SpecToolBox/4_COORDINATOR_AGENT_SPEC_TEMPLATE.md — generalized lesson added
```

## Decision Log

| Decision | Options considered | Selected option | Reason | Date |
| :--- | :--- | :--- | :--- | :--- |
| Where greetings are handled | Prompt the model to reply warmly; deterministic short-circuit in code | **Deterministic, no LLM call** | One correct reply exists; free and zero-variance beats a call for it | 2026-09-27 |
| Scope of the greeting detector | Any message containing a greeting word; only messages composed *entirely* of greeting-vocabulary words | **Entirely composed of greeting words** | Must never swallow a real request that happens to start with "hi" | 2026-09-27 |
| Fallback wording | Leave as-is; add a shared "what I can do" line to every unresolved case | **Shared line, reused everywhere** | Consistency by construction; one future wording change instead of three | 2026-09-27 |
| Fallback rendering | Keep `st.warning`; switch to `st.info` | **`st.info`** | The message now states a positive next step; a warning-styled box misrepresents that, especially for a greeting | 2026-09-27 |

## Out of scope
General small-talk/conversational ability beyond a bare greeting; farewells ("bye", "thanks"); multi-language greetings.

---

**Version**: 2.0 (implemented)
**Last Updated**: 2026-09-27
