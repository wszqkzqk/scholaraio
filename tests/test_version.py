from __future__ import annotations

from pathlib import Path

import tomllib

from scholaraio import __version__


def test_runtime_version_matches_project_version():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project_version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]

    assert __version__ == project_version
