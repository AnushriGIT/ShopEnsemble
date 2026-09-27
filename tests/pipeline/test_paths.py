"""Tests for safe ShopEnsemble pipeline path resolution."""

from pathlib import Path

import pytest

from app.pipeline.paths import PipelinePathError, resolve_data_root, resolve_source_path


def test_resolve_data_root_defaults_to_project_data_directory():
    root = resolve_data_root()

    assert root.name == "data"
    assert root.is_dir()


def test_resolve_source_path_rejects_root_escape(tmp_path: Path):
    (tmp_path / "data").mkdir()
    outside_file = tmp_path / "outside.csv"
    outside_file.write_text("value\n", encoding="utf-8")

    with pytest.raises(PipelinePathError, match="escapes"):
        resolve_source_path("../outside.csv", tmp_path / "data")


def test_resolve_source_path_rejects_missing_file(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()

    with pytest.raises(PipelinePathError, match="does not exist"):
        resolve_source_path("missing.csv", data_root)
