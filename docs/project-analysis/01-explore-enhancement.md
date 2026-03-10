# 方向一：Explore 模块能力增强与泛用性提升

## 现状分析

### 当前 Explore 模块架构

`explore.py` 当前仅支持**一种数据源**：通过 ISSN 从 OpenAlex 拉取单个期刊的全量论文。

```
fetch_journal(name, issn) → data/explore/<name>/papers.jsonl
                          → explore.db (paper_vectors)
                          → faiss.index + faiss_ids.json
                          → topic_model/ (BERTopic)
```

**核心流程：**

1. `_fetch_page()` — 以 `primary_location.source.issn:{issn}` 为 filter，cursor 分页拉取 OpenAlex `/works` 端点
2. 输出 JSONL（title, abstract, authors, year, doi, cited_by_count, type）
3. `build_explore_vectors()` — Qwen3 嵌入，存入 `explore.db` 的 `paper_vectors` 表
4. `build_explore_topics()` — BERTopic 聚类（复用 `topics.py`，通过 `papers_map` 参数）
5. `explore_vsearch()` — FAISS 语义搜索

### 现存局限

| 局限 | 详情 |
|------|------|
| **仅支持期刊 ISSN 查询** | 无法按主题、作者、机构、会议等维度探索 |
| **数据源单一** | 仅 OpenAlex，无法接入 Semantic Scholar / Crossref / arXiv |
| **无关键词检索** | explore 库只有 FAISS 语义搜索，没有 FTS5 关键词检索 |
| **无融合检索** | 主库有 `unified_search()`（RRF 融合），explore 库没有 |
| **无增量更新** | `fetch_journal()` 是全量拉取，无法只拉取新发表的论文 |
| **FAISS 扁平索引** | `IndexFlatIP` 对 >10 万篇论文性能下降 |
| **无跨库搜索** | 主库 vs explore 库 vs 多个 explore 库之间不能联合搜索 |

---

## 增强方案

### 增强一：多维度 OpenAlex 查询（最高优先级）

**目标：** 将 `fetch_journal` 泛化为 `fetch_explore`，支持多种 filter 维度。

**OpenAlex filter 语法天然支持组合，当前代码只用了 `primary_location.source.issn`。**

#### 实现方案

**1) 扩展 `fetch_journal()` → `fetch_explore()`**

```python
# explore.py 新增

def fetch_explore(
    name: str,
    *,
    issn: str | None = None,          # 期刊 ISSN（保持向后兼容）
    concept: str | None = None,        # OpenAlex concept ID（如 "C41008148" = Computer Science）
    topic: str | None = None,          # OpenAlex topic ID
    author: str | None = None,         # OpenAlex author ID（如 "A5023888391"）
    institution: str | None = None,    # OpenAlex institution ID（如 "I27837315" = MIT）
    keyword: str | None = None,        # 标题/摘要关键词搜索
    source_type: str | None = None,    # journal / conference / repository
    year_range: str | None = None,
    min_citations: int | None = None,  # cited_by_count 下限
    cfg: Config | None = None,
) -> int:
```

**2) 构建灵活的 filter 字符串**

```python
def _build_filter(*, issn=None, concept=None, topic=None, author=None,
                  institution=None, keyword=None, source_type=None,
                  year_range=None, min_citations=None) -> tuple[str, dict]:
    """构建 OpenAlex filter 字符串和额外 params。"""
    parts = []
    extra_params = {}

    if issn:
        parts.append(f"primary_location.source.issn:{issn}")
    if concept:
        parts.append(f"concepts.id:{concept}")
    if topic:
        parts.append(f"topics.id:{topic}")
    if author:
        parts.append(f"authorships.author.id:{author}")
    if institution:
        parts.append(f"authorships.institutions.id:{institution}")
    if source_type:
        parts.append(f"primary_location.source.type:{source_type}")
    if year_range:
        parts.append(f"publication_year:{year_range}")
    if min_citations is not None:
        parts.append(f"cited_by_count:>{min_citations}")

    if keyword:
        extra_params["search"] = keyword  # OpenAlex 的 search 参数

    return ",".join(parts), extra_params
```

**3) `_fetch_page()` 接受通用 filter**

当前 `_fetch_page(issn, page, year_range, cursor)` 改为 `_fetch_page(filt, extra_params, cursor)`。

**4) `meta.json` 记录查询参数**

```python
# meta.json 中记录完整查询参数，方便增量更新
{
    "name": "turbulence-2020",
    "query": {
        "concept": "C62520636",      # Turbulence
        "year_range": "2020-2025",
        "min_citations": 10
    },
    "count": 3200,
    "fetched_at": "2026-03-10T..."
}
```

**5) CLI 扩展**

```bash
# 按概念（学科领域）
scholaraio explore fetch --name turbulence --concept C62520636 --year-range 2020-2025

# 按机构
scholaraio explore fetch --name mit-ml --institution I27837315 --concept C41008148

# 按作者
scholaraio explore fetch --name hinton-works --author A5048491430

# 按关键词
scholaraio explore fetch --name drag-reduction --keyword "drag reduction" --year-range 2015-2025

# 混合条件
scholaraio explore fetch --name jfm-review --issn 0022-1120 --source-type journal --min-citations 50
```

**改动文件：**
- `explore.py`：修改 `_fetch_page()` 签名，新增 `fetch_explore()` 包装 `fetch_journal()`，`fetch_journal()` 保留为向后兼容别名
- `cli.py`：`cmd_explore` 的 `fetch` 子命令新增参数
- `.claude/skills/explore/SKILL.md`：更新文档

**改动量估计：** ~150 行 Python + CLI 参数定义

---

### 增强二：Explore 库 FTS5 + 融合检索

**目标：** 让 explore 库拥有与主库相同的关键词 + 语义融合检索能力。

**当前问题：** `explore_vsearch()` 只做纯语义搜索。对于精确匹配（论文标题、作者姓名、特定术语）效果不佳。

#### 实现方案

**1) 在 `explore.db` 中创建 FTS5 虚拟表**

```python
# explore.py 新增
def _ensure_fts(db_path: Path):
    """在 explore.db 中创建 FTS5 索引。"""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                paper_id UNINDEXED,
                title,
                authors,
                year UNINDEXED,
                abstract,
                tokenize='unicode61'
            )
        """)
```

**2) `build_explore_vectors()` 时同步构建 FTS5**

在现有的嵌入构建流程中，同步将 papers.jsonl 中的数据写入 FTS5 表。
增量逻辑：检查 `papers_fts` 中的 rowid 数量与 `papers.jsonl` 行数比对。

**3) 新增 `explore_search()` 和 `explore_unified_search()`**

```python
def explore_search(name: str, query: str, *, top_k: int = 20, cfg=None) -> list[dict]:
    """FTS5 关键词搜索 explore 库。"""
    ...

def explore_unified_search(name: str, query: str, *, top_k: int = 20, cfg=None) -> list[dict]:
    """RRF 融合搜索 explore 库（FTS5 + FAISS）。"""
    # 复用 index.py 中的 RRF 融合逻辑
    fts_results = explore_search(name, query, top_k=top_k, cfg=cfg)
    vec_results = explore_vsearch(name, query, top_k=top_k, cfg=cfg)
    return _rrf_merge(fts_results, vec_results, top_k=top_k)
```

**4) CLI 扩展**

```bash
scholaraio explore search --name jfm "drag reduction"        # 语义（保持现有行为）
scholaraio explore search --name jfm "drag reduction" --mode keyword   # 关键词
scholaraio explore search --name jfm "drag reduction" --mode unified   # 融合
```

**改动文件：**
- `explore.py`：新增 ~100 行（FTS5 构建 + 关键词搜索 + 融合）
- `cli.py`：`explore search` 子命令新增 `--mode` 参数

---

### 增强三：增量更新

**目标：** 已有 explore 库只拉取新增论文，不重新拉取全量。

#### 实现方案

```python
def fetch_explore(name, ..., incremental: bool = True):
    meta_path = explore_dir / "meta.json"
    if incremental and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        last_fetched = meta.get("fetched_at", "")
        # OpenAlex 支持 from_updated_date filter
        # 也可以用 publication_year 做增量
        if last_fetched:
            extra_filter = f",from_updated_date:{last_fetched[:10]}"
    ...
    # 追加写入 papers.jsonl（而非覆盖）
    # DOI 去重：加载已有 DOI 集合，跳过重复
    existing_dois = _load_existing_dois(jsonl_path)
    ...
```

**关键点：**
- OpenAlex 支持 `from_updated_date` 和 `from_created_date` filter
- 追加写入 JSONL，基于 DOI 去重
- 增量后需要重建 FTS5 + FAISS（仅新增部分 append）
- `meta.json` 更新 `fetched_at` 和 `count`

**改动量估计：** ~80 行

---

### 增强四：跨库搜索（中优先级）

**目标：** 在多个 explore 库 + 主库之间联合搜索。

```python
def cross_search(query: str, *, sources: list[str] | None = None,
                 top_k: int = 20, cfg=None) -> list[dict]:
    """跨库搜索。sources 为 explore 库名列表，None 表示搜索所有。"""
    results = []

    # 1. 搜索主库
    main_results = unified_search(query, top_k=top_k, cfg=cfg)
    for r in main_results:
        r["source"] = "main"
    results.extend(main_results)

    # 2. 搜索所有/指定 explore 库
    for explore_name in _list_explore_libs(cfg):
        if sources and explore_name not in sources:
            continue
        try:
            er = explore_unified_search(explore_name, query, top_k=top_k, cfg=cfg)
            for r in er:
                r["source"] = f"explore:{explore_name}"
            results.extend(er)
        except Exception:
            continue

    # 3. RRF 重新排序
    return _rrf_merge_multi(results, top_k=top_k)
```

这个功能可以延后实现，因为它依赖于增强二（explore 库的融合检索）。

---

### 增强五：大规模语料 FAISS 优化（低优先级）

当前 `IndexFlatIP` 对 <10 万篇论文足够。如果 explore 库扩展到百万级：

```python
def _build_faiss_index(vectors, ids, *, large_scale: bool = False):
    if large_scale and len(vectors) > 100_000:
        # IVF 索引：训练 + 量化
        quantizer = faiss.IndexFlatIP(dim)
        nlist = min(int(len(vectors) ** 0.5), 4096)
        index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(vectors)
        index.add(vectors)
        index.nprobe = min(nlist // 4, 64)
    else:
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
    return index
```

**建议：** 暂不实施。当前场景（单期刊全量 ~5k-50k 篇）不需要。可以在 `config.yaml` 中预留 `explore.faiss_type: flat | ivf` 配置项。

---

## 实施优先级建议

| 优先级 | 增强项 | 改动量 | 收益 |
|--------|--------|--------|------|
| P0 | 多维度 OpenAlex 查询 | ~150 行 | 从"期刊探索"变为"任意学术领域探索" |
| P1 | FTS5 + 融合检索 | ~100 行 | 精确查询能力，与主库对齐 |
| P2 | 增量更新 | ~80 行 | 避免重复拉取，降低 API 消耗 |
| P3 | 跨库搜索 | ~60 行 | 全局视角，依赖 P1 |
| P4 | FAISS 优化 | ~30 行 | 仅大规模场景需要 |

**总改动量：** ~400 行 Python + CLI 参数 + skill 文档更新

---

## 兼容性与迁移

- `fetch_journal()` 保留为 `fetch_explore(issn=issn)` 的别名，**零破坏**
- 已有 explore 库（`papers.jsonl`）格式不变
- FTS5 表是新增的，对已有 `explore.db` 无影响（首次搜索时自动创建）
- CLI 新增参数均为可选，不影响现有用法
