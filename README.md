<div align="center">

<!-- TODO: Replace with actual logo when available -->
<!-- <img src="docs/assets/logo.png" width="200" alt="ScholarAIO Logo"> -->

# ScholarAIO

**Your research terminal. Search, read, analyze, and write — all in natural language.**

[English](README.md) | [中文](README_CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP Tools](https://img.shields.io/badge/MCP_Tools-31-green.svg)](scholaraio/mcp_server.py)
[![Claude Code Skills](https://img.shields.io/badge/Claude_Code_Skills-22-purple.svg)](.claude/skills/)

</div>

---

ScholarAIO turns [Claude Code](https://docs.anthropic.com/en/docs/claude-code) into a full research terminal. Drop PDFs, ask questions, discover connections, draft your literature review — one terminal, start to finish.

<!-- TODO: Add demo GIF here -->
<!-- <div align="center">
  <img src="docs/assets/demo.gif" width="700" alt="ScholarAIO Demo">
</div> -->

## Quick Start

```bash
# 1. Install
git clone https://github.com/ZimoLiao/scholaraio.git && cd scholaraio
pip install -e ".[full]"

# 2. Configure
cp config.local.example.yaml config.local.yaml
# Add your API keys (both optional — see Configuration below)

# 3. Go
claude    # Launch Claude Code in the project directory — that's it
```

> Or use the CLI directly: `scholaraio search "your topic"` | MCP server: `scholaraio-mcp`

## What It Does

|  | Feature | Details |
|--|---------|---------|
| **PDF Parsing** | Deep structure extraction | [MinerU](https://github.com/opendatalab/MinerU) → Markdown with figures, tables, LaTeX equations preserved |
| **Hybrid Search** | Keyword + semantic fusion | FTS5 + Qwen3 embeddings + FAISS → RRF ranking |
| **Topic Discovery** | Auto-clustering | BERTopic + 6 interactive HTML visualizations |
| **Journal Exploration** | Full-journal survey | OpenAlex multi-filter fetch → embed → cluster → search |
| **Citation Graph** | References & impact | Forward/backward citations, shared references across your library |
| **Layered Reading** | Read at the depth you need | L1 metadata → L2 abstract → L3 conclusion → L4 full text |
| **Multi-Source Import** | Bring your library | Endnote XML/RIS, Zotero (API + SQLite), PDF, Markdown |
| **Workspaces** | Organize for projects | Paper subsets with scoped search and BibTeX export |
| **Academic Writing** | AI-assisted drafting | Literature review, paper sections, citation check, rebuttal, gap analysis |
| **MCP Server** | 31 tools | Works with Claude Desktop, Cursor, and any MCP client |

## How It Works

```
PDF → MinerU → Structured Markdown (figures + LaTeX intact)
                    ↓
          Metadata extraction (regex + LLM cross-validation)
          API enrichment (Crossref / Semantic Scholar / OpenAlex)
                    ↓
          DOI dedup → data/papers/<Author-Year-Title>/
                    ↓
      ┌─────────────┼─────────────┐
   FTS5 Index    FAISS Vectors   BERTopic
   (keyword)     (semantic)      (clustering)
      └─────────────┼─────────────┘
                    ↓
        Claude Code / MCP / CLI
```

## Configuration

Main config: `config.yaml` (tracked). Secrets: `config.local.yaml` (gitignored).

| Key | Purpose | Get it |
|-----|---------|--------|
| `DEEPSEEK_API_KEY` | LLM — metadata extraction, enrichment, academic discussion | [DeepSeek](https://platform.deepseek.com/) (default) or any OpenAI-compatible API |
| `MINERU_API_KEY` | PDF → structured Markdown | Free at [mineru.net](https://mineru.net/apiManage/token) or [self-host](https://github.com/opendatalab/MinerU) |

> **Both are optional.** Without LLM: regex-only extraction. Without MinerU: place `.md` files in `data/inbox/` directly.

Embedding model (Qwen3-Embedding-0.6B, ~1.2 GB) auto-downloads on first use. Default source: ModelScope (no proxy needed in China). International users: set `embed.source: huggingface` in config.

Full config reference → [`config.yaml`](config.yaml)

## Three Ways to Use

| Mode | Best for | Command |
|------|----------|---------|
| **Claude Code** (recommended) | Full research workflow — conversational | `claude` in project dir |
| **MCP Server** | Claude Desktop / Cursor integration | `scholaraio-mcp` |
| **CLI** | Scripting, quick queries | `scholaraio --help` |

<details>
<summary><strong>CLI command reference</strong></summary>

```
scholaraio index              Build FTS5 search index
scholaraio search QUERY       Keyword search
scholaraio search-author NAME Search by author
scholaraio vsearch QUERY      Semantic vector search
scholaraio usearch QUERY      Unified search (keyword + semantic fusion)
scholaraio show PAPER         View paper content (L1-L4)
scholaraio embed              Generate semantic vectors
scholaraio pipeline           Run ingestion pipeline
scholaraio explore            Journal exploration (OpenAlex)
scholaraio topics             BERTopic topic modeling
scholaraio refs PAPER         View references
scholaraio citing PAPER       View citing papers
scholaraio shared-refs A B    Shared references between papers
scholaraio top-cited          Rank by citation count
scholaraio refetch            Re-fetch citation counts from APIs
scholaraio export             Export BibTeX
scholaraio ws                 Workspace management
scholaraio audit              Data quality audit
scholaraio repair             Fix metadata
scholaraio rename             Standardize directory names
scholaraio enrich-toc         Extract table of contents
scholaraio enrich-l3          Extract conclusions
scholaraio backfill-abstract  Backfill missing abstracts
scholaraio import-endnote     Import from Endnote
scholaraio import-zotero      Import from Zotero
scholaraio attach-pdf         Attach PDF to existing paper
scholaraio setup              Setup wizard
scholaraio metrics            View LLM usage stats
```

</details>

## Project Structure

```
scholaraio/          # Python package
  cli.py             # CLI entry point (30 subcommands)
  mcp_server.py      # MCP server (31 tools)
  ingest/            # PDF parsing + metadata pipeline
  index.py           # FTS5 full-text search
  vectors.py         # Qwen3 semantic embeddings + FAISS
  topics.py          # BERTopic topic modeling
  loader.py          # L1-L4 layered paper loading
  explore.py         # OpenAlex journal exploration
  workspace.py       # Workspace management
  export.py          # BibTeX export
  audit.py           # Data quality auditing

.claude/skills/      # 22 Claude Code skills (AgentSkills.io format)
data/papers/         # Your paper library (gitignored)
data/inbox/          # Drop PDFs here for ingestion
```

## Why ScholarAIO?

| | Traditional workflow | Zotero / Endnote | ScholarAIO |
|--|---------------------|------------------|------------|
| **Ingest PDFs** | Manual rename & organize | Import + manual tagging | Drop PDF → auto-parse, extract metadata, deduplicate |
| **Search** | Ctrl+F in each PDF | Title/author search | Keyword + semantic + fusion search across full text |
| **Discover connections** | Read everything yourself | Manual collections | Auto topic clustering, citation graph, shared references |
| **Write literature review** | Copy-paste from papers | Copy-paste from papers | AI drafts from your library with real citations |
| **Export references** | Manual BibTeX entry | Built-in export | One command, filtered by workspace/year/journal |
| **Interaction** | Mouse + menus | Mouse + menus | Natural language in terminal |

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Citation

If you use ScholarAIO in your research, please cite:

```bibtex
@software{scholaraio,
  author = {Liao, Zi-Mo},
  title = {ScholarAIO: AI-Native Research Terminal},
  year = {2026},
  url = {https://github.com/ZimoLiao/scholaraio},
  license = {MIT}
}
```

## License

[MIT](LICENSE) © 2026 Zi-Mo Liao
