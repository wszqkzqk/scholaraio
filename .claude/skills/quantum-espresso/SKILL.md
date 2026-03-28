---
name: quantum-espresso
description: Run first-principles DFT calculations with Quantum ESPRESSO. Covers SCF, band structure, DOS, phonon dispersion (DFPT), electron-phonon coupling, Fermi surface, and charge density visualization. Use when the user wants to calculate electronic structure, phonon properties, superconductivity, or optical properties of materials.
version: 1.0.0
author: ZimoLiao/scholaraio
license: MIT
tags: ["scientific-computing", "dft", "quantum-espresso", "condensed-matter", "first-principles"]
---

# Quantum ESPRESSO 第一性原理计算

用 Quantum ESPRESSO 做 DFT / DFPT：基态、能带、DOS、声子、电声耦合、费米面和电荷密度分析。

本 skill **故意保持轻量**：
- 它负责告诉 agent 什么时候该用 QE、标准计算链路是什么、哪些物理与数值规范不能忽略
- 它**不**承担输入文件字段和程序参数手册的职责
- 具体输入变量、namelist 字段、程序差异统一去查 `scholaraio toolref`

## 前置条件

```bash
# 安装
conda install -c conda-forge qe
# 或编译 GPU 版（推荐 A100）

# 赝势下载
# PseudoDojo NC (DFPT 推荐): http://www.pseudo-dojo.org/
# SSSP Efficiency: https://www.materialscloud.org/discover/sssp
```

验证：`pw.x --version` 应显示版本。GPU 版本确认 CUDA 支持。

## 何时使用

适合：
- 晶体材料的电子结构、能带、DOS、声子、超导、电荷密度
- 需要第一性原理精度、并能接受较高计算成本的任务

不适合：
- 需要大尺度长时间分子动力学时，优先经典 MD
- 只是想快速试错而没有结构、赝势、收敛策略时，不要直接上正式算例

## Toolref 优先

当 agent 不确定 QE 输入变量、程序名、namelist 所属、默认值或适用条件时，**先查 toolref**。

常用查法：

```bash
scholaraio toolref search qe "wavefunction cutoff"
scholaraio toolref show qe pw ecutwfc
scholaraio toolref show qe pw occupations
scholaraio toolref show qe ph tr2_ph
scholaraio toolref show qe matdyn asr
```

推荐习惯：
- 写 `.in` 文件前，先查关键变量
- 不靠旧博客记忆 `SYSTEM` / `ELECTRONS` / `INPUTPH` 字段
- 程序切换时先确认变量属于 `pw.x`、`ph.x`、`matdyn.x` 还是别的模块

## 核心工作流

### 知识库协作模式

1. 用 `scholaraio usearch "<材料名称> DFT"` 检索相关论文
2. 从论文提取：晶体结构、交换关联泛函、k 网格、截断能、实验基准值
3. 在输入文件注释中标注参数来源
4. 计算完成后与实验数据（晶格常数、能带间隙、声子频率）对比

### 计算流程

```
SCF (pw.x)           → 基态电荷密度
  ├─ NSCF (pw.x)     → 能带/DOS 的本征值
  │   ├─ bands.x     → 能带结构后处理
  │   ├─ dos.x       → 态密度
  │   ├─ projwfc.x   → 投影态密度（轨道分辨）
  │   └─ fs.x        → 费米面 (.bxsf)
  ├─ Phonons (ph.x)  → DFPT 声子计算
  │   ├─ q2r.x       → 实空间力常数
  │   ├─ matdyn.x    → 声子色散插值
  │   └─ e-ph        → 电声耦合 (α²F, λ, Tc)
  └─ pp.x            → 电荷密度/ELF 后处理
```

建议工作流：
1. 从论文或数据库确定结构、磁性、泛函、赝势候选
2. 先做 SCF 与收敛测试
3. 再做 NSCF / 能带 / DOS
4. 需要振动性质时做 DFPT
5. 需要超导分析时做电声耦合和 Tc 估算
6. 最后统一和实验或文献做定量对比

### 关键任务类型

- 基态性质：总能、晶格常数、磁矩、应力
- 能带 / DOS / PDOS：电子结构解释
- 声子色散：动力学稳定性、软模、热性质
- 电声耦合：`alpha2f`, `λ`, `Tc`
- 电荷密度 / ELF / 费米面：成键与输运解释

### 电声耦合 & Tc

如果 `ph.x` 中设了 `electron_phonon = 'interpolated'`，会输出 `alpha2f.dat`（Eliashberg 谱函数）。

从 α²F(ω) 计算：
```
λ = 2 ∫ α²F(ω)/ω dω
ωlog = exp[(2/λ) ∫ α²F(ω) ln(ω)/ω dω]
Tc = (ωlog/1.2) × exp[-1.04(1+λ) / (λ - μ*(1+0.62λ))]
```

Allen-Dynes 公式中 μ* = 0.10-0.15（Coulomb 伪势），**必须讨论 μ* 敏感性**。

### 典型查询点

- `ecutwfc`, `ecutrho`, `occupations`, `smearing`, `degauss`
- `conv_thr`, `mixing_beta`
- `tr2_ph`, `ldisp`, `electron_phonon`
- `asr` 与后处理程序的变量位置

这些都应该通过 `toolref` 查询当前版本定义。

## 赝势选择

| 类型 | 优点 | 缺点 | 何时用 |
|------|------|------|--------|
| NC (Norm-Conserving) | DFPT 最干净 | 截断能较高 | 声子计算 |
| US (Ultrasoft) | 截断能低 | DFPT 可用但更复杂 | 大体系 SCF |
| PAW | 最准确 | QE 中 DFPT 支持有限 | 精确能带 |

**科学规范：声子计算优先用 NC 赝势。**

## 并行策略

```bash
# k 点并行（最常用）
mpirun -np 16 pw.x -npool 4 < scf.in > scf.out
# 每 pool 处理 1/4 的 k 点

# ph.x 并行
mpirun -np 16 ph.x -npool 4 < ph.in > ph.out
# 可加 -nimage 对 q 点/不可约表示并行
```

GPU 版 `pw.x`：每 GPU 一个 MPI rank，`-npool = N_GPU`。

## 可视化

| 工具 | 用途 |
|------|------|
| matplotlib | 能带结构、DOS、声子色散、α²F |
| VESTA | 电荷密度/ELF 3D 等值面 |
| XCrySDen | 费米面 (.bxsf) |
| FermiSurfer | 费米面（轨道着色） |
| ifermi (Python) | 费米面（pip 可装） |

## 科学规范

| 检查项 | 正确做法 | 常见错误 |
|--------|---------|---------|
| 截断能 | 收敛测试（总能 vs ecutwfc） | 用默认值不测试 |
| k 网格 | 收敛测试（金属需密集） | 网格太粗 |
| 展宽 | 金属用 MV，`degauss` 0.01-0.03 Ry | 用 Gaussian 展宽 |
| 赝势 | 声子用 NC（PseudoDojo） | 混用不同来源的赝势 |
| 声学求和规则 | `asr = 'crystal'` in matdyn.x | 声学支不归零 |
| μ* | 讨论 0.10-0.15 范围敏感性 | 固定一个值不讨论 |
| 晶格优化 | vc-relax 后再做性质计算 | 用实验晶格常数不优化 |

附加规范：
- 不要只给出“算出来了”，要报告收敛性与误差来源
- 不要把单次参数设置当金标准，收敛测试必须可追溯
- 对金属和绝缘体的展宽策略要明确区分

## Agent 行为准则

- 不要凭印象写 QE 输入字段，查 `toolref`
- 不要跳过收敛测试直接解读物理
- 不要把 DFT 数值结果当实验事实，必须说明泛函、赝势和近似
- 不要只给带图，要回到材料物理问题解释结果
