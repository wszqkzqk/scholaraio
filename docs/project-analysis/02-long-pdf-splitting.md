# 方向二：超长 PDF 入库——MinerU 页数限制下的自动切分与拼接

## 问题分析

### 现状

MinerU 对单次解析的页数有限制：
- **云 API**：当前未在代码中显式处理页数上限，但 MinerU 云端实际存在限制（通常 ~100 页）
- **本地 API**：`ConvertOptions` 已有 `start_page` / `end_page` 参数（0-indexed），但**从未在 pipeline 中自动使用**
- 超长文档（学位论文 200-500 页、专著 500-1000+ 页）直接提交会被 MinerU 拒绝或超时

### 当前代码中的相关基础设施

**`mineru.py` 已有的页面范围支持：**

```python
# ConvertOptions (line 166-167)
start_page: int = 0
end_page: int = 99999

# 本地 API 调用时传递 (line 246-247)
"start_page_id": (None, str(opts.start_page)),
"end_page_id": (None, str(opts.end_page)),
```

**但云 API (`convert_pdf_cloud`) 未传递 `start_page` / `end_page`** — 它的 payload 中不包含页面范围。

**`pipeline.py` 中的 `step_mineru` 直接调用 `convert_pdf()`，不做任何页数检查。**

---

## 设计目标

1. **完全透明**：用户把超长 PDF 放入 inbox，pipeline 自动处理，无需手动干预
2. **鲁棒无技术债**：切分/拼接逻辑必须正确处理边界情况
3. **保持一致性**：无论多少页，最终产出的 `paper.md` 和 `meta.json` 与普通论文结构完全一致
4. **图片引用正确**：MinerU 提取的图片路径在拼接后仍然正确
5. **幂等可重入**：如果中途失败，可以从断点恢复

---

## 实现方案

### 总体策略：分片解析 → 合并 Markdown

```
超长 PDF (500 页)
    ↓
探测页数 (PyMuPDF / pikepdf)
    ↓
若 <= PAGE_LIMIT → 直接走现有流程
    ↓
若 > PAGE_LIMIT → 按 PAGE_LIMIT 切分为多个页面范围
    ↓
逐片段调用 MinerU（复用 start_page/end_page）
    ↓
合并所有片段的 Markdown + 图片
    ↓
输出单个 paper.md + 合并的 images/
    ↓
继续正常 pipeline（extract → dedup → ingest）
```

### 方案对比：物理切分 vs 页面范围

| 方案 | 优点 | 缺点 |
|------|------|------|
| **A: 物理切分 PDF** | 独立文件，可并行发送云 API | 需要 PyMuPDF/pikepdf 依赖；跨页元素可能断裂 |
| **B: 页面范围参数** | 不需要额外依赖（本地 API 已支持）| 云 API 可能不支持；串行处理 |
| **推荐：A + B 混合** | 本地 API 用 B，云 API 用 A | 两套逻辑 |

**推荐方案：物理切分 PDF（方案 A）**，原因：
1. 云 API 和本地 API 统一处理逻辑
2. 物理切分后可以利用云 API 的 batch 能力并行处理
3. PyMuPDF (`pymupdf`) 是轻量依赖，且 MinerU 本身也需要它

### 详细实现

#### 第一步：PDF 页数探测（`mineru.py` 新增）

```python
def _get_pdf_page_count(pdf_path: Path) -> int:
    """获取 PDF 页数。优先用 pymupdf，降级为 pikepdf。"""
    try:
        import pymupdf  # PyMuPDF
        with pymupdf.open(pdf_path) as doc:
            return len(doc)
    except ImportError:
        pass
    try:
        import pikepdf
        with pikepdf.open(pdf_path) as pdf:
            return len(pdf.pages)
    except ImportError:
        pass
    _log.warning("cannot detect page count (install pymupdf or pikepdf)")
    return -1  # unknown，走原流程碰运气
```

#### 第二步：PDF 物理切分（`mineru.py` 新增）

```python
# 可配置的页数上限
DEFAULT_CHUNK_SIZE = 100  # 每片段最大页数

def _split_pdf(pdf_path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE,
               output_dir: Path | None = None) -> list[Path]:
    """将超长 PDF 切分为多个短 PDF。

    Args:
        pdf_path: 原始 PDF 路径。
        chunk_size: 每个片段的最大页数。
        output_dir: 切分后的临时目录，默认在 pdf_path 同级下创建。

    Returns:
        切分后的 PDF 路径列表，按页码顺序排列。
        如果总页数 <= chunk_size，返回 [pdf_path]（不切分）。
    """
    import pymupdf

    page_count = _get_pdf_page_count(pdf_path)
    if page_count <= chunk_size:
        return [pdf_path]

    if output_dir is None:
        output_dir = pdf_path.parent / f".{pdf_path.stem}_chunks"
    output_dir.mkdir(parents=True, exist_ok=True)

    chunks = []
    with pymupdf.open(pdf_path) as src_doc:
        for start in range(0, page_count, chunk_size):
            end = min(start + chunk_size, page_count)  # exclusive
            chunk_name = f"{pdf_path.stem}_p{start:04d}-{end-1:04d}.pdf"
            chunk_path = output_dir / chunk_name

            if chunk_path.exists():
                # 幂等：已经切分过的片段直接复用
                chunks.append(chunk_path)
                continue

            chunk_doc = pymupdf.open()
            chunk_doc.insert_pdf(src_doc, from_page=start, to_page=end - 1)
            chunk_doc.save(str(chunk_path))
            chunk_doc.close()
            chunks.append(chunk_path)

    _log.info("split %s (%d pages) into %d chunks of %d pages",
              pdf_path.name, page_count, len(chunks), chunk_size)
    return chunks
```

#### 第三步：Markdown 合并（`mineru.py` 新增）

```python
def _merge_chunk_results(
    chunk_results: list[ConvertResult],
    original_pdf: Path,
    output_dir: Path,
) -> ConvertResult:
    """将多个片段的 MinerU 输出合并为单个结果。

    处理：
    1. Markdown 文本拼接（加入分页标记）
    2. 图片文件去重合并（重命名避免冲突）
    3. content_list 合并
    4. 失败片段的错误聚合

    Args:
        chunk_results: 各片段的 ConvertResult 列表（已按页码排序）。
        original_pdf: 原始完整 PDF 的路径。
        output_dir: 最终输出目录。

    Returns:
        合并后的 ConvertResult。
    """
    merged = ConvertResult(pdf_path=original_pdf)
    final_md_path = output_dir / (original_pdf.stem + ".md")
    final_images_dir = output_dir / "images"

    md_parts: list[str] = []
    errors: list[str] = []
    total_elapsed = 0.0
    image_counter = 0

    for idx, cr in enumerate(chunk_results):
        total_elapsed += cr.elapsed_seconds

        if not cr.success:
            errors.append(f"chunk {idx}: {cr.error}")
            continue

        if not cr.md_path or not cr.md_path.exists():
            errors.append(f"chunk {idx}: md file not found")
            continue

        chunk_md = cr.md_path.read_text(encoding="utf-8", errors="replace")

        # 处理图片路径重映射
        chunk_images_dir = cr.md_path.parent / "images"
        if not chunk_images_dir.exists():
            # MinerU 也可能把图片放在 {stem}_mineru_images/
            chunk_images_dir = cr.md_path.parent / f"{cr.md_path.stem}_mineru_images"

        if chunk_images_dir.exists() and chunk_images_dir.is_dir():
            final_images_dir.mkdir(parents=True, exist_ok=True)
            for img_file in sorted(chunk_images_dir.iterdir()):
                if img_file.is_file():
                    # 重命名：chunk_idx_原始文件名
                    new_name = f"c{idx:02d}_{img_file.name}"
                    new_path = final_images_dir / new_name
                    shutil.copy2(img_file, new_path)
                    # 替换 markdown 中的图片引用
                    old_ref = f"images/{img_file.name}"
                    new_ref = f"images/{new_name}"
                    chunk_md = chunk_md.replace(old_ref, new_ref)
                    # 也处理 _mineru_images/ 的情况
                    old_ref2 = f"{cr.md_path.stem}_mineru_images/{img_file.name}"
                    chunk_md = chunk_md.replace(old_ref2, new_ref)
                    image_counter += 1

        md_parts.append(chunk_md)

    if not md_parts:
        merged.error = "all chunks failed: " + "; ".join(errors)
        merged.elapsed_seconds = total_elapsed
        return merged

    # 拼接 Markdown（不加分隔符——MinerU 输出的 md 本身有标题结构）
    final_md = "\n\n".join(md_parts)
    final_md_path.write_text(final_md, encoding="utf-8")

    merged.success = True
    merged.md_path = final_md_path
    merged.elapsed_seconds = total_elapsed

    if errors:
        _log.warning("some chunks failed during merge: %s", "; ".join(errors))

    return merged
```

#### 第四步：集成到 `convert_pdf()`（修改 `mineru.py`）

```python
def convert_pdf(pdf_path: Path, opts: ConvertOptions, *,
                chunk_size: int = DEFAULT_CHUNK_SIZE) -> ConvertResult:
    """PDF → Markdown 转换。超长 PDF 自动切分。"""
    result = ConvertResult(pdf_path=pdf_path)
    ...

    # === 新增：超长 PDF 自动切分 ===
    page_count = _get_pdf_page_count(pdf_path)
    if page_count > chunk_size:
        _log.info("long PDF detected (%d pages > %d limit), splitting...",
                  page_count, chunk_size)
        return _convert_long_pdf(pdf_path, opts, chunk_size=chunk_size)

    # === 原有逻辑 ===
    ...


def _convert_long_pdf(pdf_path: Path, opts: ConvertOptions,
                      chunk_size: int = DEFAULT_CHUNK_SIZE) -> ConvertResult:
    """处理超长 PDF：切分 → 逐片段转换 → 合并。"""
    out_dir = opts.output_dir if opts.output_dir else pdf_path.parent
    chunks_dir = out_dir / f".{pdf_path.stem}_chunks"

    # 1. 切分
    chunk_paths = _split_pdf(pdf_path, chunk_size=chunk_size,
                             output_dir=chunks_dir)

    # 2. 逐片段转换
    chunk_results = []
    for i, chunk_pdf in enumerate(chunk_paths):
        _log.info("converting chunk %d/%d: %s", i + 1, len(chunk_paths),
                  chunk_pdf.name)
        chunk_opts = ConvertOptions(
            api_url=opts.api_url,
            output_dir=chunks_dir,  # 输出到临时目录
            backend=opts.backend,
            lang=opts.lang,
            parse_method=opts.parse_method,
            formula_enable=opts.formula_enable,
            table_enable=opts.table_enable,
            save_content_list=opts.save_content_list,
            force=opts.force,
            dry_run=opts.dry_run,
        )
        # 直接调用原始转换逻辑（不递归）
        cr = _convert_single_pdf(chunk_pdf, chunk_opts)
        chunk_results.append(cr)

    # 3. 合并
    merged = _merge_chunk_results(chunk_results, pdf_path, out_dir)

    # 4. 清理临时文件
    if merged.success and chunks_dir.exists():
        shutil.rmtree(chunks_dir)
        _log.debug("cleaned up chunks dir: %s", chunks_dir)

    return merged
```

**重构要点：** 将现有 `convert_pdf()` 中的核心转换逻辑提取为 `_convert_single_pdf()`，然后 `convert_pdf()` 变为：检测页数 → 分发到 single 或 long 路径。

#### 第五步：云 API 批量并行（修改 `mineru.py`）

```python
def _convert_long_pdf_cloud(pdf_path: Path, opts: ConvertOptions, *,
                            api_key: str, cloud_url: str,
                            chunk_size: int = DEFAULT_CHUNK_SIZE) -> ConvertResult:
    """超长 PDF 云 API 处理：切分 → 批量上传 → 合并。"""
    out_dir = opts.output_dir if opts.output_dir else pdf_path.parent
    chunks_dir = out_dir / f".{pdf_path.stem}_chunks"

    # 1. 切分
    chunk_paths = _split_pdf(pdf_path, chunk_size=chunk_size,
                             output_dir=chunks_dir)

    # 2. 利用现有的 batch API 并行处理
    chunk_opts = ConvertOptions(
        output_dir=chunks_dir,
        backend=opts.backend,
        lang=opts.lang,
        parse_method=opts.parse_method,
        formula_enable=opts.formula_enable,
        table_enable=opts.table_enable,
        save_content_list=opts.save_content_list,
    )
    batch_results = convert_pdfs_cloud_batch(
        chunk_paths, chunk_opts,
        api_key=api_key, cloud_url=cloud_url,
    )

    # 3. 合并（按原始页码顺序）
    # chunk_paths 已经是有序的，batch_results 对应顺序一致
    merged = _merge_chunk_results(batch_results, pdf_path, out_dir)

    # 4. 清理
    if merged.success and chunks_dir.exists():
        shutil.rmtree(chunks_dir)

    return merged
```

**关键优势：** 利用现有的 `convert_pdfs_cloud_batch()` 函数，一个 500 页 PDF 切成 5 个 100 页片段，通过 batch API 并行处理，总耗时接近单片段耗时。

#### 第六步：Pipeline 集成（修改 `pipeline.py`）

**无需修改 `pipeline.py`**。因为切分逻辑封装在 `convert_pdf()` / `convert_pdf_cloud()` 内部，对外接口不变。`step_mineru` 调用 `convert_pdf()` 或 `convert_pdf_cloud()` 时，内部自动检测并处理超长 PDF。

```python
# step_mineru 现有代码不需要改动：
def step_mineru(ctx: InboxCtx) -> StepResult:
    ...
    result = convert_pdf(ctx.pdf_path, opts)  # 内部自动处理超长 PDF
    ...
```

#### 第七步：配置项（修改 `config.py`）

```python
@dataclass
class IngestConfig:
    ...
    chunk_page_limit: int = 100  # 超长 PDF 切分阈值

# config.yaml 示例
ingest:
  chunk_page_limit: 100  # 每片段最大页数（默认 100）
```

---

## 边界情况处理

### 1. 切分点跨页表格/图片

MinerU 的版面分析是逐页进行的，切分 PDF 后每片段的 MinerU 输出是独立的。跨页表格可能被切断。

**缓解策略：** 页面重叠（overlap）

```python
OVERLAP_PAGES = 2  # 片段之间重叠 2 页

def _split_pdf_with_overlap(pdf_path, chunk_size, overlap=OVERLAP_PAGES):
    """带重叠的切分。"""
    for start in range(0, page_count, chunk_size - overlap):
        end = min(start + chunk_size, page_count)
        ...
```

但重叠会带来合并时的去重复杂度。**建议：先不做重叠**，因为：
- 学位论文和专著的章节边界通常在偶数页
- MinerU 对跨页表格的处理本身就不完美
- 100 页的切分粒度足够粗，跨页问题概率低

### 2. 部分片段失败

```python
# _merge_chunk_results 中已处理：
if not md_parts:
    merged.error = "all chunks failed"  # 全部失败 → 报错
elif errors:
    _log.warning("some chunks failed")  # 部分失败 → 警告，继续合并成功的部分
```

**建议行为：**
- 全部失败 → `StepResult.FAIL`
- 部分失败 → 合并成功部分，日志警告，继续 pipeline
- 用户可以通过 `--force` 重试

### 3. 切分后的元数据提取

**不受影响。** `step_extract` 从合并后的 `paper.md` 中提取元数据，此时已经是完整文档。RobustExtractor 的 LLM 调用只读取前 50k 字符，与文档总长无关。

### 4. 临时文件清理

```python
# 成功后清理
if merged.success:
    shutil.rmtree(chunks_dir)  # 删除 .{stem}_chunks/

# 失败后保留（用于调试和重试）
# chunks_dir 以 . 开头，不会被 pipeline 误识别为待处理文件
```

### 5. 磁盘空间

一个 100MB 的 PDF 切分成 5 片，临时占用 ~500MB（原 PDF + 5 个片段 PDF + 5 个片段 MD）。合并成功后清理至 ~120MB（原 PDF + 合并 MD + 图片）。

**建议：** 在切分前检查磁盘空间，如果可用空间 < PDF 大小 × 6，发出警告。

### 6. PyMuPDF 依赖

PyMuPDF (`pymupdf`) 是 MinerU 的传递依赖，通常已安装。如果未安装：

```python
def _split_pdf(pdf_path, chunk_size, output_dir):
    try:
        import pymupdf
    except ImportError:
        raise ImportError(
            "pymupdf is required for splitting long PDFs. "
            "Install it with: pip install pymupdf"
        )
```

---

## 完整改动清单

| 文件 | 改动 | 行数估计 |
|------|------|----------|
| `ingest/mineru.py` | 新增 `_get_pdf_page_count()`, `_split_pdf()`, `_merge_chunk_results()`, `_convert_long_pdf()`, `_convert_long_pdf_cloud()` | ~200 行 |
| `ingest/mineru.py` | 重构 `convert_pdf()` 提取 `_convert_single_pdf()` | ~20 行改动 |
| `ingest/mineru.py` | 修改 `convert_pdf_cloud()` 添加长 PDF 检测 | ~15 行 |
| `config.py` | `IngestConfig` 新增 `chunk_page_limit` | ~3 行 |
| `config.yaml` | 新增默认值 | ~2 行 |

**总改动：~240 行新增 + ~20 行重构**

---

## 测试策略

```python
# tests/test_pdf_split.py

def test_get_page_count():
    """测试页数检测。"""

def test_split_short_pdf():
    """短 PDF（< chunk_size）不切分，返回 [原路径]。"""

def test_split_long_pdf():
    """500 页 PDF 切分为 5 个 100 页片段。"""

def test_split_idempotent():
    """重复切分不生成新文件。"""

def test_merge_markdown():
    """多个 MD 片段正确合并。"""

def test_merge_images():
    """图片路径正确重映射。"""

def test_merge_partial_failure():
    """部分片段失败仍能合并成功部分。"""

def test_convert_long_pdf_e2e():
    """端到端测试：超长 PDF → 切分 → 转换 → 合并 → 单个 paper.md。"""
```

---

## 与现有流程的兼容性

- **Pipeline (`step_mineru`)：** 无需修改，切分逻辑封装在 `convert_pdf()` 内部
- **Cloud batch (`_process_inbox`)：** 需要小改——如果检测到超长 PDF，从 batch 列表中移除，单独处理
- **元数据提取：** 不受影响（从合并后的 md 提取）
- **图片引用：** 通过重命名保证唯一性
- **CLI 参数：** 可选新增 `--chunk-size N`，默认值来自配置
