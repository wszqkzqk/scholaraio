<div align="center">

<!-- TODO: 有 logo 后替换 -->
<!-- <img src="docs/assets/logo.png" width="200" alt="ScholarAIO Logo"> -->

# ScholarAIO

**你的科研终端。检索、阅读、分析、写作——全部用自然语言完成。**

[English](README.md) | [中文](README_CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP Tools](https://img.shields.io/badge/MCP_Tools-31-green.svg)](scholaraio/mcp_server.py)
[![Claude Code Skills](https://img.shields.io/badge/Claude_Code_Skills-22-purple.svg)](.claude/skills/)

</div>

---

ScholarAIO 把 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 变成一个完整的科研终端。放入 PDF，提出问题，发现关联，起草综述——一个终端，从头到尾。

<!-- TODO: 加 demo GIF -->
<!-- <div align="center">
  <img src="docs/assets/demo.gif" width="700" alt="ScholarAIO Demo">
</div> -->

## 快速开始

```bash
# 1. 安装
git clone https://github.com/ZimoLiao/scholaraio.git && cd scholaraio
pip install -e ".[full]"

# 2. 配置
cp config.local.example.yaml config.local.yaml
# 填入 API key（均为可选，见下方配置说明）

# 3. 启动
claude    # 在项目目录启动 Claude Code，开始对话
```

> 也可以直接用 CLI：`scholaraio search "你的主题"` | MCP 服务器：`scholaraio-mcp`

## 核心功能

|  | 功能 | 说明 |
|--|------|------|
| **PDF 解析** | 深度结构提取 | [MinerU](https://github.com/opendatalab/MinerU) → Markdown，图表、公式完整保留 |
| **融合检索** | 关键词 + 语义 | FTS5 + Qwen3 嵌入 + FAISS → RRF 排序融合 |
| **主题发现** | 自动聚类 | BERTopic + 6 种交互式 HTML 可视化 |
| **期刊探索** | 全量期刊调研 | OpenAlex 多维过滤 → 向量化 → 聚类 → 语义搜索 |
| **引用图谱** | 参考文献与影响力 | 正向/反向引用、共同引用分析 |
| **分层阅读** | 按需加载 | L1 元数据 → L2 摘要 → L3 结论 → L4 全文 |
| **多源导入** | 带上你的文献库 | Endnote XML/RIS、Zotero（API + SQLite）、PDF、Markdown |
| **工作区** | 按项目组织 | 论文子集管理，支持范围内检索和 BibTeX 导出 |
| **学术写作** | AI 辅助撰写 | 文献综述、论文章节、引用验证、审稿回复、研究空白分析 |
| **MCP 服务器** | 31 个工具 | Claude Desktop、Cursor 等 MCP 客户端均可调用 |

## 工作流程

```
PDF → MinerU → 结构化 Markdown（图表 + LaTeX 公式保留）
                    ↓
          元数据提取（正则 + LLM 交叉验证）
          API 补全（Crossref / Semantic Scholar / OpenAlex）
                    ↓
          DOI 去重 → data/papers/<Author-Year-Title>/
                    ↓
      ┌─────────────┼─────────────┐
   FTS5 索引      FAISS 向量     BERTopic
   （关键词）     （语义）       （聚类）
      └─────────────┼─────────────┘
                    ↓
        Claude Code / MCP / CLI
```

## 配置说明

主配置：`config.yaml`（进 git）。敏感信息：`config.local.yaml`（不进 git）。

| Key | 用途 | 获取方式 |
|-----|------|---------|
| `DEEPSEEK_API_KEY` | LLM——元数据提取、内容富化、学术讨论 | [DeepSeek](https://platform.deepseek.com/)（默认）或任意 OpenAI 兼容 API |
| `MINERU_API_KEY` | PDF → 结构化 Markdown | [mineru.net](https://mineru.net/apiManage/token) 免费申请，也可[本地部署](https://github.com/opendatalab/MinerU) |

> **均为可选。** 没有 LLM key：降级为纯正则提取。没有 MinerU key：直接将 `.md` 放入 `data/inbox/`。

嵌入模型（Qwen3-Embedding-0.6B，约 1.2 GB）首次使用时自动下载。默认从 ModelScope 下载（国内无需代理），海外用户设置 `embed.source: huggingface`。

完整配置参考 → [`config.yaml`](config.yaml)

## 三种使用方式

| 模式 | 适用场景 | 命令 |
|------|---------|------|
| **Claude Code**（推荐） | 完整科研工作流——对话式交互 | 项目目录下运行 `claude` |
| **MCP 服务器** | Claude Desktop / Cursor 集成 | `scholaraio-mcp` |
| **CLI** | 脚本、快速查询 | `scholaraio --help` |

<details>
<summary><strong>CLI 命令一览</strong></summary>

```
scholaraio index              构建 FTS5 检索索引
scholaraio search QUERY       关键词检索
scholaraio search-author NAME 按作者搜索
scholaraio vsearch QUERY      语义向量检索
scholaraio usearch QUERY      融合检索（关键词 + 语义）
scholaraio show PAPER         查看论文内容（L1-L4）
scholaraio embed              生成语义向量
scholaraio pipeline           运行入库流水线
scholaraio explore            期刊探索（OpenAlex）
scholaraio topics             BERTopic 主题建模
scholaraio refs PAPER         查看参考文献
scholaraio citing PAPER       查看被引论文
scholaraio shared-refs A B    共同参考文献分析
scholaraio top-cited          按引用量排序
scholaraio refetch            重新查询引用量
scholaraio export             导出 BibTeX
scholaraio ws                 工作区管理
scholaraio audit              数据质量审计
scholaraio repair             修复元数据
scholaraio rename             标准化目录名
scholaraio enrich-toc         提取目录结构
scholaraio enrich-l3          提取结论段
scholaraio backfill-abstract  补全缺失摘要
scholaraio import-endnote     从 Endnote 导入
scholaraio import-zotero      从 Zotero 导入
scholaraio attach-pdf         为已有论文补充 PDF
scholaraio setup              环境配置向导
scholaraio metrics            查看 LLM 用量统计
```

</details>

## 项目结构

```
scholaraio/          # Python 包
  cli.py             # CLI 入口（30 个子命令）
  mcp_server.py      # MCP 服务器（31 个工具）
  ingest/            # PDF 解析 + 元数据流水线
  index.py           # FTS5 全文检索
  vectors.py         # Qwen3 语义嵌入 + FAISS
  topics.py          # BERTopic 主题建模
  loader.py          # L1-L4 分层加载
  explore.py         # OpenAlex 期刊探索
  workspace.py       # 工作区管理
  export.py          # BibTeX 导出
  audit.py           # 数据质量审计

.claude/skills/      # 22 个 Claude Code Skills（AgentSkills.io 格式）
data/papers/         # 你的论文库（不进 git）
data/inbox/          # 放入 PDF 即可入库
```

## 为什么选 ScholarAIO？

| | 传统工作流 | Zotero / Endnote | ScholarAIO |
|--|-----------|------------------|------------|
| **导入 PDF** | 手动重命名、整理 | 导入 + 手动标签 | 放入 PDF → 自动解析、提取元数据、去重 |
| **检索** | 每篇 PDF 里 Ctrl+F | 标题/作者搜索 | 关键词 + 语义 + 融合检索，覆盖全文 |
| **发现关联** | 全靠自己读 | 手动建分组 | 自动主题聚类、引用图谱、共同引用分析 |
| **写文献综述** | 从论文里复制粘贴 | 从论文里复制粘贴 | AI 基于你的文献库起草，附真实引用 |
| **导出参考文献** | 手动录入 BibTeX | 内置导出 | 一条命令，按工作区/年份/期刊过滤 |
| **交互方式** | 鼠标 + 菜单 | 鼠标 + 菜单 | 终端里用自然语言 |

## 参与贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 引用

如果 ScholarAIO 对你的研究有帮助，欢迎引用：

```bibtex
@software{scholaraio,
  author = {Liao, Zi-Mo},
  title = {ScholarAIO: AI-Native Research Terminal},
  year = {2026},
  url = {https://github.com/ZimoLiao/scholaraio},
  license = {MIT}
}
```

## 许可证

[MIT](LICENSE) © 2026 Zi-Mo Liao
