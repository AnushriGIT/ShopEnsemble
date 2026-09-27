---
name: review-fix-loop
description: Performs a systematic, cost-controlled, and security-gated code review, remediation, and verification loop over recent code changes or specific files.
---

# AI-Assisted Code Review & Remediation Loop Skill

## Goal
Execute a bounded, security-gated code review and auto-remediation cycle to find, fix, and verify issues in code changes before commit.

## Workflow Steps

### Step 1: Scope Gate
Check if the changes touch:
- Authentication or authorization logic
- File or image uploads/preprocessing
- Secrets, tokens, or private environment variables
- External untrusted inputs (e.g. public API endpoints)
If YES, a **Security Gate** (Step 5) is mandatory.

### Step 2: Review Pass 1
Analyze the code changes under review at **medium effort** by default. For each finding, output:
- File and line number
- Severity (`Critical`, `Warning`, `Advice`)
- A concrete failure scenario
Classify findings as `CONFIRMED` (clear bugs) or `PLAUSIBLE` (ambiguous smells).

### Step 3: Fix
- Automatically fix `CONFIRMED` findings.
- Escalate `PLAUSIBLE` findings to the user for human decision before patching.

### Step 4: Bounded Re-Review
Run up to 2 more review passes over the fixed code:
- If a pass returns zero findings, exit the loop immediately.
- If findings remain after 3 total passes, stop and present the remaining findings to the user. Do not loop infinitely.

### Step 5: Security Gate
If mandated in Step 1, run a dedicated security scan/STRIDE threat model assessment on the **final** diff to catch secrets leaks, injections, and validation boundaries.

### Step 6: Human Checkpoint
Present:
1. The consolidated list of findings, marked as `fixed`, `skipped`, or `no_change_needed`.
2. The final clean diff.
3. An explicit request for user approval to commit. Do not auto-commit.
