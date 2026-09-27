---
name: test-suite-generator
description: Discover a project's own conventions, requirements, and known-bug history, then generate an outcome-based test suite for it — instead of requiring a hand-written, project-specific prompt each time. Use when asked to "write tests for this project/module", "generate a test suite", or "add regression coverage" without the user having already specified exactly what to test and how. Portable across projects — copy this whole skill folder into any new repo's `.agents/skills/`.
---

# Test Suite Generator

Generates a test suite by *discovering* a project's context first, rather than requiring the user to hand-write a detailed prompt (file list, mocking strategy, known edge cases) every time. The discovery step is the reusable part — it's what makes this portable across projects instead of being one-off advice for a single codebase.

## Step 0 — Scope

This skill targets exactly what's named in the request — a single function, a single class, one file, a handful of files, or (only if explicitly asked) an entire module/project. It never defaults to "the whole project" on its own. If no target is given at all, **ask** which file/class/function to focus on rather than assuming everything — scanning an entire codebase unprompted is the test-generation equivalent of always running a review at `ultra` effort instead of `medium`: expensive and unfocused when a narrower target was probably intended.

A narrower scope also narrows every later step accordingly — Step 1's history-mining still searches the whole project for a review log (that's cheap and context, not scope), but Step 2's plan and Step 4's generated files only ever cover the named target.

## Step 1 — Context Discovery

Before writing any test, gather:

1. **Test framework & convention already in use.** Look for `tests/`, `pyproject.toml`/`package.json`/`jest.config.*` test config, and existing test files. Match their naming pattern (e.g. `test_<module>.py`), fixture style, and mocking library already adopted — don't introduce a second convention.
2. **Known-bug / review history.** Search for a changelog-like artifact: a review log (`reviewLog.md`, `CHANGELOG.md`), recent commit messages, or an issue tracker export. Mine it for specific bugs already found and fixed — each one becomes a regression test. This is the highest-value, most project-specific step: it turns analysis someone already did into test cases for free, instead of re-discovering the same bugs from scratch.
3. **Public surface of the target file(s).** Walk the functions/classes/API endpoints that are actually reachable from outside the module — that's what needs contract coverage, not private helpers unless they carry real risk (validation, math, state transitions).
4. **What needs mocking.** Grep target files' imports for expensive/non-deterministic dependencies: network calls, model-loading libraries (e.g. `torch.hub`, HTTP model APIs), database clients, filesystem paths tied to one machine, real datasets. Anything in this category gets mocked so the suite runs fast, deterministically, and portably — never assume the real dependency is available in CI or on another machine.

## Step 2 — Draft the Test Plan

Synthesize what Step 1 found into a concrete list before writing code:
- Core logic correctness (math, transformations, ranking/sorting — anything with one correct answer for a given input)
- Edge cases: boundary values, empty/None inputs, error paths, guards that are supposed to fail loudly
- Contract behavior for anything with an external interface (API status codes, function signatures, exceptions raised)
- One regression test per known bug found in Step 1's history-mining
- The mocking strategy decided in Step 1

## Step 3 — Plan Review (Human Checkpoint, before any code is written)

Present the Step 2 test plan to the user before generating anything — same principle as the Day 4 "TDD Planning Gate": the agent presents the plan for approval *before* generating code, not after. Show, per target file:
- What will be covered (grouped: core logic, edge cases, contract behavior, regression tests from history-mining)
- What will be mocked, and why
- Anything Step 1 couldn't determine confidently (ambiguous convention, no test framework detected, no history artifact found) — flag it here rather than guessing silently

Wait for explicit go-ahead or adjustments before moving to Step 4. This is cheap insurance: catching a wrong assumption (wrong mocking target, missing a file, wrong convention) here costs one message; catching it after a full suite is generated costs a regeneration.

## Step 4 — Generate

Write the tests under the discovered test directory, following the discovered naming/fixture conventions. Prefer one test file per source module unless the project's existing convention says otherwise.

**Before writing any file, check whether it already exists.** If a test file with the target name is already present, do **not** silently overwrite it — stop and ask whether to merge into it, append new test cases, or pick a different name. Silently overwriting could destroy existing test coverage someone already wrote, and that's not recoverable by anything later in this flow.

**Every generated test case gets a brief comment stating what it's checking and why — one line, not a docstring essay.** A test's assertions show *what* is being checked; they rarely show *why* this specific case matters, which is exactly the part a future reader can't recover on their own. Concretely:
- Regression tests: cite the source finding, e.g. `# Regression test for reviewLog.md v1 finding #4: DATASET_BASE_PATH was hardcoded...`
- Edge-case tests: name the specific condition being forced, e.g. `# Empty gallery — must return [] instead of raising`
- Tests relying on non-obvious mocking: one line on what's faked and why, e.g. `# conftest.py's fake read_csv gives GALLERY_PATHS length 3`
- Plain happy-path/contract tests where the function name already says it all (e.g. `test_l2_normalize_unit_length`) don't need a comment — don't restate the name in prose.

## Step 5 — Bounded Run → Triage → Fix Loop

Run the generated suite and investigate every failure before touching anything — don't reflexively "fix" a failing test without first knowing why it failed. This loop is bounded and exits early, same discipline as a code-review loop, applied to test generation instead of bug-fixing:

1. Run the test framework's CLI (e.g. `pytest`).
2. For each failure, **triage the root cause before acting** — don't guess. If the cause isn't obvious from the traceback alone, apply a systematic debugging approach (this environment's `obra-superpowers-systematic-debugging` skill, if available, or an equivalent root-cause-first method) rather than trial-and-error patching. Every failure falls into exactly one of two categories:
   - **Test-authoring mistake** (bad mock, wrong fixture, import error, wrong expected value, non-determinism in the test itself) → fix the test, re-run.
   - **Genuine bug in the source code** the test is exercising → do **not** weaken the test or "fix" it to match the buggy behavior just to turn it green. This is a real finding, not noise — carry it forward to Step 6 exactly like a code-review finding (what's broken, concrete failure scenario), never silently buried.
3. **Never edit source/production code as part of this loop, under any circumstances** — only the generated test files are in scope for auto-fixing. If a failure seems to call for a source-code change to pass, that's by definition the "genuine bug" case above, not a test-authoring mistake — surface it, don't act on it.
4. If a pass comes back clean (or only fails on cases that are *supposed* to fail, i.e. intentional negative tests) — **stop immediately**.
5. Hard cap at **3 total passes**. If real issues of either kind remain after that, stop anyway and hand them to the user rather than looping indefinitely.
6. Optional: if the project has a coverage tool configured, check coverage of the target files and loop once more only if it's below a reasonable bar — same early-exit-on-success rule applies.

## Step 6 — Human Checkpoint

Report, don't just declare done:
- What's covered, file by file
- What's mocked and why
- **Any genuine bugs the suite uncovered in the source code** (from Step 5's triage) — surfaced prominently, never folded silently into "tests passing"
- Any gaps or known-history items that couldn't be turned into a test (and why)
- Never auto-commit the generated tests — present them for review first, same as any other code change
- Never silently patch source code just to make a test pass — a genuine bug found this way goes to the human, same never-auto-fix-without-surfacing principle as `review-fix-loop`

## Step 7 — Persist to a Tracking Log

Don't let the rationale for these changes live only in this conversation — write a versioned entry recording the run before finishing:

- Append to a dedicated, versioned log (e.g. `.agents/memory-bank/testGenerationLog.md`, following the same append-only convention as this project's code-review log if one exists — `v1`, `v2`, ...; never edit a past entry, add a new one). If the project has no such convention yet, create the file rather than skipping this step — the point is durability, not matching an exact name.
- Record: target file(s), what was covered and why (tie back to Step 1's discovery — e.g. "regression test for the bug found in reviewLog.md v3"), what was mocked and why, any genuine bugs uncovered in Step 5, the final pass/fail state, and whether the generated tests were committed.
- This is the same principle as `review-fix-loop`'s tracking — a human should be able to find out later *why* a test exists without re-reading the whole conversation that created it.
