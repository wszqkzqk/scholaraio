# Next Session Handoff

> Updated: 2026-03-31
>
> Purpose:
> - record what has been completed in the current `v1.3.0-scientific-skills` push
> - make the next Codex session resumable without rereading the whole branch

## What Was Completed

### 1. `toolref` hardening for mature tools

The following tools were pushed to a much more production-ready state:

- Quantum ESPRESSO
- LAMMPS
- GROMACS
- OpenFOAM

Key outcomes:

- QE `show/search` now prefers exact program + parameter hits
- LAMMPS now resolves common natural aliases correctly:
  - `fix npt -> fix_nh`
  - `pair style eam -> pair_eam`
- GROMACS `mdp-options.rst` parsing was upgraded so important parameter pages are no longer skeletal:
  - `pcoupl`
  - `tcoupl`
  - `constraints`
- GROMACS natural-language search now maps better to parameter pages:
  - `Parrinello Rahman -> pcoupl`
  - `v-rescale thermostat -> tcoupl`
  - `nose-hoover thermostat -> tcoupl`
  - `constraints h-bonds -> constraints`
- OpenFOAM manifest coverage was expanded and actually pulled locally:
  - `simpleFoam`
  - `yPlus`
  - `wallShearStress`
  - `residuals`
- OpenFOAM manifest refresh logic was hardened so failed pages can be restored from existing cache instead of silently dropping previously fetched pages

Current local OpenFOAM state:

- `python -m scholaraio.cli toolref list openfoam`
- result: `2312 (current) — 16 页 [16/16 已索引]`

### 2. Scientific skill architecture was clarified

The project now has a clearer split between:

- tool-specific scientific skills
- `toolref`
- runtime fallback behavior

New artifacts:

- `docs/internal/scientific-cli-skill-spec.md`
- `.claude/skills/scientific-runtime/SKILL.md`

`scientific-tool-onboarding` was updated to point to those two as the default standard.

### 3. Existing scientific skills were upgraded toward `toolref-first`

Updated skills:

- `quantum-espresso`
- `lammps`
- `gromacs`
- `openfoam`
- `bioinformatics`

They now more explicitly say:

- the agent should use `toolref` first
- the user should not be asked to maintain `toolref`
- coverage gaps are maintenance issues, not user obligations

## Verification Already Run

These passed in the current session:

- `python -m pytest tests/test_toolref.py -q`
- `python -m pytest tests/test_toolref.py tests/test_cli_messages.py -q`

Also manually validated:

- `toolref list/show/search` flows for QE
- `toolref list/show/search` flows for LAMMPS
- `toolref list/show/search` flows for GROMACS
- `toolref list/show/search` flows for OpenFOAM

## What Is Still Not Done

### 1. Bioinformatics `toolref` is still the weakest area

Current limitation:

- it is still more like a curated multi-tool bundle than a mature, high-confidence toolref layer
- coverage and routing across sub-tools are not yet at the same level as QE / LAMMPS / GROMACS / OpenFOAM

This is the next most important `toolref` gap.

### 2. Scientific runtime protocol is documented, but not yet fully propagated

We now have:

- a spec
- a runtime skill
- onboarding references

But not every future scientific skill will automatically inherit this unless we keep enforcing it during onboarding and review.

### 3. Launch readiness still depends on demo execution, not only docs/toolref quality

The code/documentation/tooling side has moved forward, but launch-prep still needs real execution evidence:

- run logs
- validation tables
- final assets
- frozen numbers

## Recommended Next Step

Start with **Bioinformatics toolref productionization**.

Why:

- it is now the least mature scientific toolref layer
- it affects a multi-tool workflow, so user experience can still fragment badly there
- the scientific skills and runtime protocol are now strong enough to support a proper cleanup pass

## First Commands For The Next Session

Start here:

```bash
git status --short
python -m scholaraio.cli toolref list bioinformatics
python -m scholaraio.cli toolref search bioinformatics "bootstrap tree"
python -m scholaraio.cli toolref search bioinformatics "variant calling"
python -m scholaraio.cli toolref show bioinformatics iqtree command-reference
python -m scholaraio.cli toolref show bioinformatics samtools sort
```

Then inspect:

- `.claude/skills/bioinformatics/SKILL.md`
- `scholaraio/toolref.py`
- `tests/test_toolref.py`

## Next Session Goal

Push Bioinformatics to the same standard as the mature toolrefs:

- natural-language search should route to the correct sub-tool
- top queries should hit useful primary pages
- partial fetch failures should not degrade cached coverage
- the skill should stay toolchain-aware without becoming a giant manual
