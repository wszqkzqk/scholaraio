# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Code quality toolchain: ruff, mypy, pre-commit hooks
- CI workflow: lint, typecheck, test matrix (Python 3.10–3.12)
- Contract-level test suite (33 tests)
- Community governance: CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
- GitHub issue/PR templates
- CITATION.cff for academic citation
- MkDocs documentation site with API reference
- Release workflow for PyPI publishing

## [0.1.0] — 2025-06-01

### Added
- Core knowledge base: PDF ingestion (MinerU), FTS5 search, semantic search (FAISS + Qwen3)
- L1–L4 layered content loading
- BibTeX export with filtering
- Data quality audit with structured issue reports
- BERTopic topic modeling with 6 HTML visualizations
- Citation graph (refs / citing / shared-refs)
- Workspace management for paper subsets
- Multi-dimensional literature exploration (OpenAlex integration)
- Endnote XML/RIS and Zotero import
- 22 Claude Code skills (AgentSkills.io standard)
- MCP server with 31 tools
- Bilingual setup wizard (EN/ZH)
- GPU-adaptive batch embedding with automatic profiling
