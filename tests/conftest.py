"""Shared fixtures for ScholarAIO tests.

Provides temporary paper directories and sample metadata so that tests
are fully isolated from user data.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub the `mcp` package so modules that import it can be loaded without the
# real SDK installed.  Set __path__ on each stub so Python treats them as
# packages (required for sub-package imports like `from mcp.server.fastmcp
# import FastMCP`).  FastMCP is stubbed as a minimal class whose .tool()
# returns an identity decorator so decorated functions are preserved.
# ---------------------------------------------------------------------------


try:
    from mcp.server.fastmcp import FastMCP as _  # noqa: F401
except ImportError:
    # Real mcp SDK not installed — inject a minimal stub so modules that
    # import it can be loaded.  The stub is only installed when mcp is
    # genuinely absent, preserving integration behaviour when it is present.

    class _FakeFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self):
            def decorator(fn):
                return fn

            return decorator

        run = MagicMock()

    _mcp = types.ModuleType("mcp")
    _mcp.__path__ = []  # type: ignore[attr-defined]
    _mcp_server = types.ModuleType("mcp.server")
    _mcp_server.__path__ = []  # type: ignore[attr-defined]
    _mcp_fastmcp = types.ModuleType("mcp.server.fastmcp")
    _mcp_fastmcp.FastMCP = _FakeFastMCP  # type: ignore[attr-defined]

    sys.modules["mcp"] = _mcp
    sys.modules["mcp.server"] = _mcp_server
    sys.modules["mcp.server.fastmcp"] = _mcp_fastmcp


@pytest.fixture()
def tmp_papers(tmp_path: Path) -> Path:
    """Create a temporary papers directory with two sample papers."""
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()

    # Paper A — typical journal article
    pa = papers_dir / "Smith-2023-Turbulence"
    pa.mkdir()
    (pa / "meta.json").write_text(
        json.dumps(
            {
                "id": "aaaa-1111",
                "title": "Turbulence modeling in boundary layers",
                "authors": ["John Smith", "Jane Doe"],
                "first_author_lastname": "Smith",
                "year": 2023,
                "journal": "Journal of Fluid Mechanics",
                "doi": "10.1234/jfm.2023.001",
                "abstract": "We propose a novel turbulence model for boundary layers.",
                "paper_type": "journal-article",
                "citation_count": {"crossref": 10, "s2": 12},
                "volume": "950",
                "issue": "2",
                "pages": "100-120",
                "publisher": "Cambridge University Press",
                "issn": "0022-1120",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pa / "paper.md").write_text(
        "# Turbulence modeling in boundary layers\n\nFull text here.",
        encoding="utf-8",
    )

    # Paper B — thesis without DOI
    pb = papers_dir / "Wang-2024-DeepLearning"
    pb.mkdir()
    (pb / "meta.json").write_text(
        json.dumps(
            {
                "id": "bbbb-2222",
                "title": "Deep learning for fluid dynamics",
                "authors": ["Wei Wang"],
                "first_author_lastname": "Wang",
                "year": 2024,
                "journal": "",
                "doi": "",
                "abstract": "This thesis explores deep learning approaches.",
                "paper_type": "thesis",
                "citation_count": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pb / "paper.md").write_text(
        "# Deep learning for fluid dynamics\n\nThesis content.",
        encoding="utf-8",
    )

    return papers_dir


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Return a path for a temporary SQLite database."""
    return tmp_path / "index.db"
