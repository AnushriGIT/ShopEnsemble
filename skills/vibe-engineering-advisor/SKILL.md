---
name: vibe-engineering-advisor
description: Apply Vibe Engineering principles when designing agent/harness architecture, writing new SKILL.md files, reviewing context or MCP/A2A tool wiring, or debugging an agent that is misbehaving. Use it to decide "should this be a skill", "why is context degrading", or "which protocol fits this integration" — not for general coding questions.
---

# Vibe Engineering Advisor

Procedural memory for applying the Vibe Engineering curriculum (Days 1–5) to real decisions on this project. This skill does not duplicate the knowledge base — it tells you which document to pull and what to check, on-demand, instead of keeping that content in static context every turn.

## Source of truth
- [.agents/memory-bank/vibeEngineering.md](../../memory-bank/vibeEngineering.md) — core concepts: context engineering, memory primitives, protocol map (MCP/A2A/A2UI/AP2/UCP), security patterns.
- [.agents/memory-bank/vibeEngineeringAssignments.md](../../memory-bank/vibeEngineeringAssignments.md) — concrete codelab walkthroughs (CLI setup, skills lifecycle, ADK agents, secure coding, deployment).

## When an agent is failing or misbehaving
Follow the **debugging hierarchy** from Day 1 before touching prompts or swapping models:
1. **Context** — is the right information actually reaching the model? (most common root cause)
2. **Tools** — are tools/MCP servers configured correctly? Use MCP Inspector to check.
3. **Prompts** — only tune after ruling out 1 and 2.
4. **Model** — last resort.

## When deciding "should this be a skill?"
Ask: is this a **procedural** capability (how to do a repeatable thing), not static knowledge or one-off info?
- If yes, and it needs deterministic correctness (validation, formatting rules) → prefer scripting the logic and having the skill call the script (Level 4 pattern: `database-schema-validator`), not relying on LLM judgment.
- If it needs a reusable asset (license header, template) → bundle the asset alongside `SKILL.md` (Level 2 pattern).
- If it needs consistent output shape from sparse instruction → give few-shot input/output examples in the skill (Level 3 pattern).
- If it's just an instruction/convention → a plain instruction-only skill is enough (Level 1 pattern, e.g. `git-commit-formatter`).
- Full walkthroughs for all four levels are in `vibeEngineeringAssignments.md` (Day 3, entry 5).

## When reviewing context / harness design
- Treat the active context window as a **budget**, not a vessel — a 1M-token window can degrade well before it's full. Prefer moving info to dynamic context (skills, RAG, MCP) over cramming it into static context (`AGENTS.md`, system prompt) unless it's needed on every turn.
- Classify new memory as **episodic** (session/log history), **semantic** (RAG/knowledge base), or **procedural** (a Skill) — put it in the matching primitive rather than defaulting to system prompt text.

## When wiring integrations
Pick the protocol by what's being connected, per the Day 2 protocol map:
- Agent ↔ Tool → **MCP**
- Agent ↔ Agent → **A2A**
- Agent → dynamic UI → **A2UI**
- Agent-driven payments → **AP2**
- Agent ↔ merchant catalog/orders → **UCP**

## When writing security-sensitive agent code
Pull the pattern from `vibeEngineeringAssignments.md` Day 4 (entry 8): pre-commit secret scanning (Semgrep), a `PreToolUse` hook blocking destructive shell commands, and a STRIDE threat-model skill — apply the same shape here rather than ad hoc checks.
