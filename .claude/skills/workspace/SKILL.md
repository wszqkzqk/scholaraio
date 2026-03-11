---
name: workspace
description: Manage workspace paper subsets — create workspaces, add/remove papers, search within a workspace, and export BibTeX. Workspaces are thin layers that reference papers in the main library by UUID. Use when the user wants to organize papers into groups for writing, review, or focused analysis.
---

# 工作区管理

工作区是论文子集管理工具。每个工作区引用主库中的论文（通过 UUID），支持在子集内搜索和导出。

## 执行逻辑

### 创建工作区

```bash
scholaraio ws init <名称>
```

### 添加论文

```bash
scholaraio ws add <名称> <论文标识...>
```

论文标识可以是：DOI、目录名、UUID、或搜索关键词（模糊匹配）。

### 移除论文

```bash
scholaraio ws remove <名称> <论文标识...>
```

### 列出所有工作区

```bash
scholaraio ws list
```

### 查看工作区论文

```bash
scholaraio ws show <名称>
```

### 在工作区内搜索

```bash
scholaraio ws search <名称> "<查询词>" [--top N] [--year YYYY] [--journal 期刊名]
```

使用融合检索（关键词 + 语义），范围限定在工作区论文内。

### 导出工作区 BibTeX

```bash
scholaraio ws export <名称> [--year YYYY] [--journal 期刊名]
```

## 示例

用户说："帮我建一个 drag reduction 的工作区"
→ 执行 `ws init drag-reduction`

用户说："把这几篇论文加到工作区"
→ 执行 `ws add drag-reduction <DOI或目录名...>`

用户说："在工作区里搜 turbulent boundary layer"
→ 执行 `ws search drag-reduction "turbulent boundary layer"`

用户说："导出工作区的引用"
→ 执行 `ws export drag-reduction`

用户说："我有哪些工作区"
→ 执行 `ws list`
