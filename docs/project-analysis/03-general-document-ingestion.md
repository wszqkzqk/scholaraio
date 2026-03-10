# 方向三：普通文档入库流程——非论文 PDF/Markdown 的检索化处理

## 问题分析

### 当前系统假设

ScholarAIO 的入库流程建立在一个核心假设上：**入库的是学术论文**。

这体现在：

1. **元数据提取** (`extractor.py`)：提取 title / authors / year / DOI / journal —— 全是论文特有字段
2. **API 补全** (`_api.py`)：通过 Crossref / S2 / OpenAlex 查询 —— 这些 API 只索引学术出版物
3. **去重逻辑** (`step_dedup`)：以 DOI 为核心 —— 非论文文档没有 DOI
4. **兜底路径** (`step_dedup`)：没有 DOI → LLM 判断是否 thesis → 不是 thesis → 移入 `pending/` 等待人工处理
5. **嵌入和检索** (`vectors.py`)：以 `title + abstract` 构建向量 —— 非论文文档可能两者都没有

**结论：** 当前系统对非论文文档（技术报告、课程讲义、标准文档、书籍章节、个人笔记、会议记录等）**没有正式的入库路径**。它们要么卡在 pending，要么需要用户手动编造 DOI 来绕过去重。

### 用户场景

| 文档类型 | 特点 | 示例 |
|----------|------|------|
| 技术报告 | 有标题/作者，无 DOI/期刊 | NASA Technical Report, NIST SP |
| 课程讲义/教材章节 | 有标题，无作者/年份 | MIT OCW 课件 |
| 标准文档 | 有编号（ISO/GB），无 DOI | ISO 9001:2015 |
| 个人笔记/草稿 | 可能无标题/作者 | 研究记录、会议纪要 |
| 书籍 | 有 ISBN，无 DOI | 专著的单独章节 |
| 白皮书/行业报告 | 有标题/机构，无学术元数据 | McKinsey 报告 |
| 预印本 | 有 arXiv ID，可能无 DOI | arXiv:2301.12345 |

---

## 设计方案

### 核心思路：引入 `paper_type: "document"` 并建立专用流程

不新建一套独立系统，而是**复用现有基础设施**，通过 `paper_type` 扩展让非论文文档融入现有检索体系。

### 架构概览

```
data/inbox-doc/           ← 新增入口
├── report.pdf
├── notes.md
└── slides.pdf
        ↓
    step_mineru            (PDF → MD，与论文相同)
        ↓
    step_extract_doc       ← 新增步骤（替代 step_extract）
    │  尝试常规提取
    │  → 失败/信息不足 → LLM 从全文生成 title + summary
        ↓
    step_ingest_doc        ← 复用 step_ingest（跳过 DOI 去重）
        ↓
    data/papers/{Author-Year-Title}/   (统一存储)
    ├── meta.json          (paper_type: "document")
    ├── paper.md
    └── images/
```

### 第一步：新增 `data/inbox-doc/` 入口

类似 `data/inbox-thesis/`，新增一个专用 inbox：

```python
# pipeline.py _process_inbox 中新增

# Process document inbox (data/inbox-doc/)
doc_inbox = cfg._root / "data" / "inbox-doc"
if doc_inbox.exists():
    _process_inbox(
        doc_inbox, papers_dir, pending_dir, existing_dois,
        per_file_steps_doc, global_steps, cfg, opts,
        is_document=True,  # 新增标记
    )
```

**为什么新建 inbox 而非改造现有 inbox？**
- 用户意图明确：放进 `inbox-doc/` 的就是非论文文档，不需要 LLM 猜测
- 与 `inbox-thesis/` 设计对称
- 不影响现有论文入库流程

### 第二步：LLM 生成标题和摘要（核心新增）

**新增 `ingest/metadata/_doc_extract.py`：**

```python
"""
非论文文档的元数据提取。

对于缺少标题/摘要的普通文档，使用 LLM 从全文生成。
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scholaraio.config import Config

from scholaraio.ingest.metadata._models import PaperMetadata

_log = logging.getLogger(__name__)

# 全文截取上限（LLM 上下文窗口限制）
_MAX_TEXT_FOR_LLM = 60_000  # 约 60k 字符


def extract_document_metadata(
    md_path: Path,
    cfg: "Config",
    *,
    existing_meta: PaperMetadata | None = None,
) -> PaperMetadata:
    """从非论文文档提取/生成元数据。

    流程：
    1. 先尝试常规 regex 提取（可能得到标题、作者等）
    2. 检查提取结果是否充分（至少要有 title）
    3. 不充分时，调用 LLM 读取全文，生成 title + summary

    Args:
        md_path: Markdown 文件路径。
        cfg: 全局配置。
        existing_meta: 已有的元数据（如果有的话）。

    Returns:
        补全后的 PaperMetadata。
    """
    from scholaraio.ingest.extractor import RegexExtractor
    from scholaraio.llm import call_llm

    # Step 1: 尝试常规提取
    if existing_meta:
        meta = existing_meta
    else:
        extractor = RegexExtractor()
        meta = extractor.extract(md_path)

    text = md_path.read_text(encoding="utf-8", errors="replace")

    # Step 2: 检查是否需要 LLM 补充
    has_title = bool((meta.title or "").strip())
    has_abstract = bool((meta.abstract or "").strip())

    if has_title and has_abstract:
        _log.debug("document already has title and abstract, skipping LLM")
        meta.paper_type = meta.paper_type or "document"
        return meta

    # Step 3: LLM 生成标题和摘要
    api_key = cfg.resolved_llm_api_key()
    if not api_key:
        _log.warning("no LLM API key, cannot generate title/abstract for document")
        if not has_title:
            # 最后兜底：用文件名作为标题
            meta.title = md_path.stem.replace("-", " ").replace("_", " ")
        meta.paper_type = meta.paper_type or "document"
        return meta

    truncated = text[:_MAX_TEXT_FOR_LLM]

    prompt = _build_prompt(truncated, has_title=has_title, has_abstract=has_abstract,
                           existing_title=meta.title)

    try:
        result = call_llm(prompt, cfg, purpose="doc_extract", max_tokens=1000)
        data = _parse_llm_response(result)

        if not has_title and data.get("title"):
            meta.title = data["title"]

        if not has_abstract and data.get("summary"):
            meta.abstract = data["summary"]

        if data.get("authors"):
            meta.authors = data["authors"]
            meta.first_author = data["authors"][0] if data["authors"] else ""

        if data.get("year") and not meta.year:
            meta.year = data["year"]

        if data.get("document_type"):
            meta.paper_type = data["document_type"]
        else:
            meta.paper_type = "document"

    except Exception as e:
        _log.warning("LLM document extraction failed: %s", e)
        if not has_title:
            meta.title = md_path.stem.replace("-", " ").replace("_", " ")
        meta.paper_type = meta.paper_type or "document"

    return meta


def _build_prompt(text: str, *, has_title: bool, has_abstract: bool,
                  existing_title: str = "") -> str:
    """构建 LLM 提示词。"""
    tasks = []
    if not has_title:
        tasks.append("1. Generate a concise, descriptive **title** for this document")
    if not has_abstract:
        tasks.append(
            f"{'2' if not has_title else '1'}. Write a **summary** (150-300 words) "
            "that captures the main content, key points, and purpose of this document. "
            "This summary will be used as the document's abstract for search indexing."
        )

    task_str = "\n".join(tasks)

    return (
        "You are analyzing a document (not necessarily an academic paper). "
        "It could be a technical report, lecture notes, manual, standard, "
        "book chapter, or any other type of document.\n\n"
        f"Your tasks:\n{task_str}\n\n"
        "Also extract if present:\n"
        "- **authors**: list of author/editor names\n"
        "- **year**: publication/creation year\n"
        "- **document_type**: one of: technical-report, lecture-notes, "
        "standard, book-chapter, manual, white-paper, presentation, "
        "meeting-notes, or document (generic fallback)\n\n"
        f"{'Existing title: ' + existing_title + chr(10) if existing_title else ''}"
        "Respond in JSON format:\n"
        "```json\n"
        "{\n"
        '  "title": "...",\n'
        '  "summary": "...",\n'
        '  "authors": ["..."],\n'
        '  "year": 2024,\n'
        '  "document_type": "..."\n'
        "}\n"
        "```\n\n"
        "--- DOCUMENT CONTENT ---\n\n"
        f"{text}"
    )


def _parse_llm_response(text: str) -> dict:
    """从 LLM 回复中提取 JSON。"""
    import json
    import re

    # 提取 ```json ... ``` 块
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))

    # 尝试直接解析
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))

    return {}
```

### 第三步：修改 Pipeline 流程

**在 `pipeline.py` 中新增 `step_extract_doc`：**

```python
def step_extract_doc(ctx: InboxCtx) -> StepResult:
    """非论文文档的元数据提取（替代 step_extract + step_dedup）。"""
    if not ctx.md_path or not ctx.md_path.exists():
        return StepResult.SKIP

    from scholaraio.ingest.metadata._doc_extract import extract_document_metadata

    try:
        meta = extract_document_metadata(ctx.md_path, ctx.cfg)
    except Exception as e:
        _log.error("document extraction failed: %s", e)
        ctx.status = "failed"
        return StepResult.FAIL

    if not (meta.title or "").strip():
        _log.error("cannot determine document title")
        ctx.status = "failed"
        return StepResult.FAIL

    ctx.meta = meta
    ctx.meta.paper_type = ctx.meta.paper_type or "document"
    return StepResult.OK
```

**Document inbox 使用不同的步骤序列：**

```python
# 文档入库的步骤序列（不经过 dedup/API 查询）
DOC_STEPS = ["mineru", "extract_doc", "ingest"]
```

**在 `_process_inbox()` 中：**

```python
def _process_inbox(inbox_dir, papers_dir, pending_dir, existing_dois,
                   per_file_steps, global_steps, cfg, opts,
                   is_thesis=False, is_document=False):
    ...
    if is_document:
        per_file_steps = ["mineru", "extract_doc", "ingest"]
    ...
```

### 第四步：Document 去重策略

非论文文档没有 DOI，需要替代去重机制：

```python
def _dedup_document(meta: PaperMetadata, existing_papers: dict) -> bool:
    """基于标题相似度的文档去重。

    Returns:
        True 如果是重复的。
    """
    from difflib import SequenceMatcher

    if not meta.title:
        return False

    title_lower = meta.title.lower().strip()
    for existing_name, existing_meta in existing_papers.items():
        existing_title = (existing_meta.get("title") or "").lower().strip()
        if not existing_title:
            continue

        # 精确匹配
        if title_lower == existing_title:
            return True

        # 模糊匹配（阈值 0.9，比论文更严格因为没有 DOI 做确认）
        ratio = SequenceMatcher(None, title_lower, existing_title).ratio()
        if ratio > 0.9:
            _log.info("document title similar to existing '%s' (%.2f), skipping",
                      existing_name, ratio)
            return True

    return False
```

### 第五步：确保检索链路通畅

**嵌入向量构建 (`vectors.py`)：**

当前代码已经可以处理非论文文档：

```python
# vectors.py 中的嵌入逻辑
text = f"{title}\n\n{abstract}"
if not abstract:
    text = title  # title-only 也能嵌入
```

LLM 生成的 summary 写入 `meta.json` 的 `abstract` 字段后，语义检索自然工作。

**FTS5 索引 (`index.py`)：**

```python
# index.py build_index() 索引这些字段：
# title, authors, year, journal, abstract, conclusion
# 非论文文档：title + abstract（LLM 生成）都会被索引
```

**无需修改现有索引逻辑。**

**BibTeX 导出 (`export.py`)：**

```python
# 需要新增 document 类型映射
TYPE_MAP = {
    ...
    "document": "@misc",
    "technical-report": "@techreport",
    "book-chapter": "@inbook",
    "manual": "@manual",
    "lecture-notes": "@misc",
    "standard": "@misc",
    "white-paper": "@misc",
}
```

### 第六步：直接 Markdown 入库（无需 MinerU）

用户可能直接放 `.md` 文件到 `inbox-doc/`：

```python
# 在 _process_inbox 中，现有逻辑已处理：
# 如果 inbox 中有 .md 但没有对应的 .pdf，跳过 mineru 步骤
# step_mineru 检查 md_path 是否已存在，存在则 skip
```

**无需修改。** 用户直接放 `.md` 文件，`step_mineru` 自动跳过，直接进入 `step_extract_doc`。

### 第七步：meta.json 扩展字段

```python
# 非论文文档的 meta.json 示例
{
    "id": "uuid-...",
    "title": "LLM 生成的标题 / 文件名中提取的标题",
    "authors": ["Author Name"],              # 可能为空
    "year": 2024,                            # 可能为 null
    "doi": "",                               # 空
    "journal": "",                           # 空
    "abstract": "LLM 生成的 150-300 词摘要",  # 核心：确保检索可用
    "paper_type": "document",                # 或 technical-report, lecture-notes 等
    "extraction_method": "llm_document",     # 标记来源
    "source_file": "original-filename.pdf",

    # 以下字段为空但保持结构一致
    "volume": "",
    "issue": "",
    "pages": "",
    "publisher": "",
    "issn": "",
    "citation_count": {},
    "ids": {},
    "references": [],
    "api_sources": []
}
```

---

## 完整改动清单

| 文件 | 改动 | 行数估计 |
|------|------|----------|
| **新增** `ingest/metadata/_doc_extract.py` | LLM 文档元数据提取 | ~180 行 |
| `ingest/pipeline.py` | 新增 `step_extract_doc`，`_process_inbox` 支持 `is_document`，`inbox-doc` 处理 | ~60 行 |
| `ingest/pipeline.py` | `_dedup_document()` 标题去重 | ~30 行 |
| `config.py` | `ensure_dirs()` 新增 `data/inbox-doc/` | ~2 行 |
| `export.py` | `TYPE_MAP` 扩展 | ~8 行 |
| `cli.py` | pipeline `--list` 中展示新步骤 | ~5 行 |
| `.claude/skills/ingest/SKILL.md` | 文档更新 | 文档 |

**总改动：~285 行新增**

---

## 降级策略（无 LLM API Key）

如果用户没有配置 LLM API key：

1. **标题：** 从文件名生成（`技术报告_2024.pdf` → `"技术报告 2024"`）
2. **摘要：** 从 Markdown 前 500 词截取（类似现有 `_extract_abstract_from_md()`）
3. **paper_type：** 默认 `"document"`
4. **作者/年份：** 从文件名 regex 尝试提取（如 `Smith-2024-Report.pdf`）

```python
# 降级路径
def _fallback_document_metadata(md_path: Path) -> PaperMetadata:
    """无 LLM 时的最小元数据提取。"""
    text = md_path.read_text(encoding="utf-8", errors="replace")

    # 标题：第一个 markdown 标题或文件名
    title = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            title = line.lstrip("# ").strip()
            break
    if not title:
        title = md_path.stem.replace("-", " ").replace("_", " ")

    # 摘要：前 500 词
    words = text.split()[:500]
    abstract = " ".join(words)

    return PaperMetadata(
        title=title,
        abstract=abstract,
        paper_type="document",
    )
```

---

## 与现有系统的交互

### 搜索

```bash
# 非论文文档与论文在同一搜索空间
scholaraio search "drag reduction"           # FTS5，会命中文档的 title/abstract
scholaraio vsearch "drag reduction"          # 语义搜索，LLM 生成的 summary 参与
scholaraio usearch "drag reduction"          # 融合搜索

# 可以按 paper_type 过滤
scholaraio search "report" --type document   # 只搜索非论文文档
scholaraio search "report" --type article    # 只搜索论文
```

### 工作区

非论文文档与论文一样可以加入工作区：

```bash
scholaraio workspace add my-project <document-uuid>
```

### 审计

```python
# audit.py 需要微调：对 paper_type == "document" 的条目
# 不报 missing_doi 警告（因为文档本来就没有 DOI）
if meta.get("paper_type") in ("document", "technical-report", "lecture-notes",
                               "standard", "manual", "white-paper"):
    # skip DOI warning
    pass
```

### 引用图谱

非论文文档没有 DOI，无法参与引用图谱。这是预期行为——引用图谱本质上是学术出版物间的关系网络。

---

## 未来扩展

### ISBN 支持（书籍）

```python
# 未来可以在 _doc_extract.py 中检测 ISBN
# 然后通过 Google Books API 或 Open Library API 补全元数据
isbn_pattern = r"(?:ISBN[-: ]?)?(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx]"
```

### arXiv ID 支持（预印本）

```python
# 检测 arXiv ID，通过 arXiv API 补全
arxiv_pattern = r"(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)"
# https://export.arxiv.org/api/query?id_list=2301.12345
```

### 分段嵌入（长文档）

对于超长文档（100+ 页），单个 title+abstract 的嵌入可能无法覆盖全部内容。未来可以：

```python
# 按章节/段落切分，每段独立嵌入
# 搜索时返回最相关的段落所在文档
# 这需要修改 vectors.py 的数据模型（当前是 1 paper = 1 vector）
```

这是一个更大的架构变更，建议作为独立方向规划。

---

## 测试策略

```python
# tests/test_doc_ingest.py

def test_extract_doc_with_title_and_abstract():
    """文档已有标题和摘要，不调用 LLM。"""

def test_extract_doc_missing_title():
    """文档无标题，LLM 生成标题。"""

def test_extract_doc_missing_abstract():
    """文档无摘要，LLM 生成 summary。"""

def test_extract_doc_no_llm_fallback():
    """无 LLM API key 时的降级路径。"""

def test_dedup_document_exact_title():
    """完全相同标题的文档被去重。"""

def test_dedup_document_similar_title():
    """相似标题（>0.9）的文档被去重。"""

def test_doc_in_search_results():
    """文档可以被 FTS5 / FAISS / unified 搜索到。"""

def test_doc_bibtex_export():
    """文档导出为 @misc BibTeX 条目。"""

def test_doc_audit_no_doi_warning():
    """文档类型不报 missing_doi 警告。"""
```
