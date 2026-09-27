#!/bin/bash
# Reusable capability script for linting this project's Python source files using Ruff.
#
# The upstream template hardcoded a different project's layout (api/,
# retrieval_core.py, fashion_ds_processing.py, config.py, setup_check.py) —
# none of which exist in ShopEnsemble. Fixed to target this project's actual
# tree: app/ (includes the gitignored app/agents/, app/api/ — ruff lints
# whatever's on disk regardless of git tracking) and tests/.

FIX_ARG=""
if [ "$1" == "--fix" ]; then
  FIX_ARG="--fix"
fi

echo "Running project code linter..."
uv run --with ruff ruff check app/ tests/ $FIX_ARG
