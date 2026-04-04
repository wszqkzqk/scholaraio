"""Proceedings detection helpers."""

from __future__ import annotations

import re
from pathlib import Path

_TITLE_KEYWORDS = (
    "proceedings of",
    "conference proceedings",
    "symposium proceedings",
    "workshop proceedings",
)

_TOC_PATTERNS = (
    "table of contents",
    "contents",
)

_DOI_RE = re.compile(r"10\.\d{4,}/[^\s)]+", re.IGNORECASE)


def looks_like_proceedings_text(text: str) -> bool:
    lowered = text.lower()
    if any(keyword in lowered for keyword in _TITLE_KEYWORDS):
        return True
    if any(marker in lowered for marker in _TOC_PATTERNS) and len(set(_DOI_RE.findall(text))) >= 2:
        return True
    return len(set(_DOI_RE.findall(text))) >= 3


def detect_proceedings_from_md(md_path: Path, *, force: bool = False) -> tuple[bool, str]:
    """Detect whether a markdown file appears to represent a proceedings volume."""
    if force:
        return True, "manual_inbox"

    text = md_path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()

    if any(keyword in lowered for keyword in _TITLE_KEYWORDS):
        return True, "title_keyword"
    if any(marker in lowered for marker in _TOC_PATTERNS):
        return True, "table_of_contents"
    if len(set(_DOI_RE.findall(text))) >= 3:
        return True, "multi_doi"
    return False, ""
