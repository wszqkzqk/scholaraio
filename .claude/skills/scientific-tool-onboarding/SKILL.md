---
name: scientific-tool-onboarding
description: Use when adding or upgrading ScholarAIO support for a new scientific computing tool, especially when the work needs official docs ingestion, toolref integration, lightweight skill design, and end-to-end CLI verification
---

# Scientific Tool Onboarding

## Overview

把一个新科学工具接入 ScholarAIO，目标不是“写一份长教程”，而是形成这三个层次的闭环：

- `toolref` 能查官方接口和参数
- 对应 `skill` 能指导 agent 何时使用、如何验证
- CLI 在真实使用中足够稳，不只是测试能过

规范参考：

- tool skill 写法统一参照 [docs/internal/scientific-cli-skill-spec.md](/home/lzmo/repos/personal/scholaraio/docs/internal/scientific-cli-skill-spec.md)
- 运行时行为统一参照 `scientific-runtime` skill

## When to Use

适用于：
- 新增一个科学计算工具到 `scholaraio toolref`
- 升级某个工具的官方文档源或版本策略
- 发现现有 scientific skill 过重，需要改成 `toolref-first`

不适用于：
- 只写一篇一次性笔记
- 只修一个小 typo

## Core Workflow

### 1. 先定“官方真源”

优先级：
- 官方文档站
- 官方源码仓库中的文档目录
- 官方维护的 README / man page / PDF

不要优先用：
- 博客
- 第三方教程
- 论坛帖子

要求：
- 记录文档 URL、版本策略、格式（RST / HTML / man / Markdown / PDF）
- 判断适合 `git` 抓取还是 `manifest` 抓取

### 2. 再定“接入粒度”

问自己三个问题：
- 用户会按什么名词来查：求解器、命令、参数、字典、子工具？
- `page_name` 应该怎么命名，未来最稳？
- `program / section / title` 该怎样存，`show/search` 才顺手？

经验规则：
- `page_name` 要服务 CLI 使用体验，不要只服务抓取方便
- 一个大页面如果天然包含很多独立参数，应该拆页
- 如果工具本来就是多子工具工具链，允许一个 top-level tool 下挂多个 `program`

### 3. 先做最小 manifest / parser，不要一上来追求全量

先做高价值页面：
- 最常用求解器或主程序
- 最关键配置字典或参数页
- 最关键模型页
- 1-2 个典型后处理或分析页

先让 `list/show/search` 真正可用，再扩充覆盖率。

### 4. TDD 先测 parser 和鲁棒性边角

最低应有测试：
- 解析器能提取 title / synopsis / content
- 版本或 program 规范化逻辑
- manifest 工具的“是否完整”判断
- 失败后残缺目录不会被误判成已完成

如果没有先看到失败场景，就不知道这个工具接入点真正脆不脆。

### 5. 实现 fetch/index/show/search 全链路

最低要求：
- `fetch` 能拉取并落盘
- `list` 能看到版本和页数
- `show` 能按用户自然输入命中
- `search` 能搜到高价值页面

重点防御：
- 网络失败后的残缺目录
- manifest 页面部分失败
- program 名规范化不一致
- 页面命名和用户输入不一致

### 6. 必须做“真实使用体验”验证

不能只跑测试。必须像用户一样手动执行：

```bash
scholaraio toolref fetch <tool>
scholaraio toolref list <tool>
scholaraio toolref show <tool> <natural query>
scholaraio toolref search <tool> "<real query>"
```

检查：
- `show` 命中的是不是用户想看的页面
- 正文前是不是被导航噪音淹没
- `synopsis` 有没有信息量
- 首次失败后，第二次 `fetch` 是否会卡在脏目录

如果手感不好，就继续打磨 CLI；不要因为测试是绿的就停。

### 7. 再把对应 skill 改成轻量 `toolref-first`

对应 scientific `SKILL.md` 应只保留：
- 何时使用
- 高层工作流
- 科学规范
- `toolref` 查询入口
- agent 行为准则
- 覆盖缺口时如何退化处理

不要把 skill 写成第二份 API 手册。

分工应始终是：
- `skill = 路由 + 方法论 + 验证规范`
- `toolref = 官方接口与参数`
- `scientific-runtime = 运行时退化与用户体验协议`

### 8. 最后做发布门槛检查

一个新工具只有同时满足下面几条，才算真正接入完成：
- 官方文档已入 `toolref`
- `fetch/list/show/search` 都能真实使用
- 至少有基础 parser 测试
- 对应 skill 已改成轻量 `toolref-first`
- 至少手动体验过一次端到端 CLI

## Common Mistakes

- 只看测试，不自己用 CLI
- 第一次抓取失败后没处理脏目录
- `page_name` 为抓取方便而设计，导致 `show` 很难用
- 把 scientific skill 写成超长命令手册
- 新 skill 没有写清楚覆盖缺口时 agent 应如何继续服务用户
- 用第三方教程代替官方文档
- 把“能跑起来”误当成“生产级”

## Quick Checklist

- 官方文档源已确认
- 版本策略已确认
- 解析粒度已确认
- parser 测试已写
- `fetch/list/show/search` 已手动体验
- 残缺目录问题已验证
- 对应 skill 已改成轻量结构
- 新 skill 与 `scientific-runtime` 协议兼容
- 最终再跑一次相关测试与 CLI smoke
