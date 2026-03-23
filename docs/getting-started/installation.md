# Installation

## Requirements

- Python 3.10+
- Git

## Install from Source

```bash
git clone https://github.com/zimoliao/scholaraio.git
cd scholaraio

# Core only (search, export, audit)
pip install -e .

# Full installation (embeddings, topics, import)
pip install -e ".[full]"
```

## Optional Dependencies

| Extra | What it adds |
|-------|-------------|
| `embed` | Semantic search (sentence-transformers + FAISS) |
| `topics` | BERTopic topic modeling |
| `import` | Endnote / Zotero import |
| `mcp` | MCP server for Claude Desktop / Cursor |
| `full` | All of the above |
| `dev` | Development tools (pytest, ruff, mypy) |

## Setup Wizard

Run the interactive setup wizard to configure API keys and directories:

```bash
scholaraio setup
```

Or check what's already configured:

```bash
scholaraio setup check
```

## Agent Setup

If you want to know which path to use for Claude Code, Codex, OpenClaw, Cursor, or MCP clients, see:

- [Agent Setup](agent-setup.md)

That guide separates:

- opening this repository directly
- registering ScholarAIO for use from another project
- choosing between native skills, plugins, and MCP

## Embedding Model

The embedding model (Qwen3-Embedding-0.6B, ~1.2 GB) downloads automatically on first use. For users outside China, set `embed.source: huggingface` in `config.yaml`.
