# ScholarAIO

**Scholar All-In-One** — an AI-native research terminal for coding agents.

ScholarAIO is a research terminal built around AI coding agents. You interact with your literature knowledge base through natural language — searching, reading, analyzing, and writing — all from the command line.

## Features

- **PDF Ingestion**: Convert PDFs to structured Markdown via MinerU (cloud or local)
- **Hybrid Search**: FTS5 keyword search + FAISS semantic search + RRF fusion
- **Topic Modeling**: BERTopic clustering with interactive HTML visualizations
- **Citation Graph**: View references, citing papers, and shared references
- **BibTeX Export**: Filtered export with standard citation formats
- **Paper Translation**: Translate papers with concurrent chunked LLM calls and optional portable bundles
- **Literature Exploration**: Multi-dimensional OpenAlex queries with isolated data
- **Workspace Management**: Organize papers into subsets for focused work
- **Federated Discovery**: Search your library, explore silos, and arXiv in one flow
- **Research Insights**: Inspect search/read behavior trends and semantic neighbor recommendations
- **Scientific Tool Docs**: Query indexed official docs for scientific computing tools with `toolref`
- **Office Document Inspection**: Verify DOCX / PPTX / XLSX structure with `document inspect`
- **Agent Skills**: Reusable workflows for search, writing, scientific runtime, and more

## Quick Start

```bash
pip install -e ".[full]"
scholaraio setup
```

See [Installation](getting-started/installation.md) for detailed instructions.
See [Agent Setup](getting-started/agent-setup.md) for repo-open vs plugin setup paths.
See [Translation Guide](guide/translate.md) for translation, resume, and portable export behavior.
See [API Reference](api/index.md) for Python module documentation.

## Two Usage Modes

| Mode | Interface | Best for |
|------|-----------|----------|
| **Agent** | Claude Code CLI | Full research workflow via natural language |
| **CLI** | Terminal | Scripting and automation |
