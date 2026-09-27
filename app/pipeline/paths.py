"""Safe, configuration-driven paths for the ShopEnsemble data pipeline."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"
DATA_ROOT_ENV = "SHOPENSEMBLE_DATA_ROOT"


class PipelinePathError(ValueError):
    """Raised when a configured pipeline path is invalid or escapes its root."""


def resolve_data_root(data_root: str | Path | None = None) -> Path:
    """Resolve and validate the pipeline data root.

    Explicit arguments take precedence over ``SHOPENSEMBLE_DATA_ROOT``. When no
    override is supplied, the repository's project-relative ``data`` folder is
    used. The root must already exist and be a directory.
    """

    # Explicit arguments make tests and batch jobs deterministic; the
    # environment variable supports deployment-specific data locations.
    configured_root = data_root or os.getenv(DATA_ROOT_ENV) or DEFAULT_DATA_ROOT
    resolved_root = Path(configured_root).expanduser().resolve()
    if not resolved_root.exists():
        raise PipelinePathError(f"Data root does not exist: {resolved_root}")
    if not resolved_root.is_dir():
        raise PipelinePathError(f"Data root is not a directory: {resolved_root}")
    return resolved_root


def resolve_source_path(
    source_name: str | Path,
    data_root: str | Path | None = None,
) -> Path:
    """Resolve one source file while preventing root escapes and directories."""

    # Resolve the root first so every source path is checked against the same
    # canonical directory, including paths containing symlinks or '..'.
    root = resolve_data_root(data_root)
    candidate = Path(source_name).expanduser()
    if candidate.is_absolute():
        resolved_path = candidate.resolve()
    else:
        resolved_path = (root / candidate).resolve()

    # A resolved relative path must remain below the configured data root;
    # this blocks traversal and absolute-path escapes before file access.
    try:
        resolved_path.relative_to(root)
    except ValueError as error:
        raise PipelinePathError(
            f"Source path escapes the configured data root: {resolved_path}"
        ) from error

    if not resolved_path.exists():
        raise PipelinePathError(f"Source file does not exist: {resolved_path}")
    if not resolved_path.is_file():
        raise PipelinePathError(f"Source path is not a file: {resolved_path}")
    return resolved_path
