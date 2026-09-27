#!/bin/bash
# Reusable capability script for running test suites.
#
# Excludes `integration` (requires a live PostgreSQL instance) and `eval`
# (requires OPENAI_API_KEY and makes real, billed OpenAI calls) by default —
# this is meant to be safe to run blindly on any machine, without silently
# spending real API calls or hanging on an unreachable database just because
# OPENAI_API_KEY/Postgres happen to be configured locally. Pass extra pytest
# args (e.g. `-m eval`, a specific path) to override the default scope.
echo "Running project test runner..."
# `python -m pytest`, not the bare `pytest` executable — the bare console
# script does not add the project root to sys.path, which breaks every
# `from app...` import in this project's conftest/tests. This bit before:
# running `./.venv/bin/pytest` directly failed with
# `ModuleNotFoundError: No module named 'app'`, unrelated to test content.
if [ -f "./.venv/bin/python" ]; then
  PYTHON="./.venv/bin/python"
elif [ -f "./venv/bin/python" ]; then
  PYTHON="./venv/bin/python"
else
  PYTHON="python"
fi

if [ "$#" -gt 0 ]; then
  "$PYTHON" -m pytest "$@"
else
  "$PYTHON" -m pytest tests/ -m "not integration and not eval"
fi
