---
name: code-linter
description: Runs project-wide linting and code quality check on the project backend codebase.
---

# Code Linter Skill

Provides a utility script to run formatting and styling checks using Ruff over the workspace python files.

## Usage

Check for styling/formatting warnings:
```bash
bash .agents/skills/code-linter/scripts/lint.sh
```

Automatically fix linting/formatting errors:
```bash
bash .agents/skills/code-linter/scripts/lint.sh --fix
```
