# Scientific CLI Skill Spec

> Internal spec for ScholarAIO scientific computing skills.
>
> Goal:
> - standardize how new scientific CLI tools are integrated
> - keep tool-specific skills lightweight and user-facing
> - ensure agents can serve non-developer users without asking them to maintain `toolref`

## Problem Statement

ScholarAIO is for end users, not only tool authors or developers.

That means a scientific skill must not assume:

- the user knows the tool's CLI surface
- the user will manually improve `toolref`
- the user will stop their work to help the agent build documentation support

So every scientific CLI skill must separate three responsibilities:

- `skill`: routing, workflow, scientific norms, fallback behavior
- `toolref`: official interface and parameter reference
- `runtime protocol`: how the agent behaves when `toolref` is incomplete

## Required Layers

Every scientific tool integration should produce these layers:

1. `toolref` support
2. tool-specific scientific skill
3. runtime behavior compatible with the shared scientific runtime protocol

The order matters:

- `toolref` gives the agent a trustworthy interface source
- the tool skill tells the agent when and why to use the tool
- the runtime protocol ensures the user experience stays smooth even when coverage is partial

## What A Tool Skill Must Contain

Each scientific CLI skill must include:

### 1. Scope

- what scientific questions the tool is good for
- what questions it is not appropriate for

### 2. Agent Default Protocol

This is mandatory.

It must say:

- how the agent recognizes the task type
- how the agent chooses the relevant sub-tool or program
- that the agent should use `toolref` first
- that the agent must absorb complexity instead of pushing it onto the user

### 3. Toolref Entry Points

The skill must include a small set of representative `toolref` queries:

- at least one `search`
- at least two `show`
- examples should reflect real user phrasing, not only canonical parameter names

### 4. Fallback Behavior

This is mandatory.

The skill must say:

- if `toolref` is partial or misses a page, the agent should continue with official docs
- the agent should label the gap as a maintenance or coverage issue
- the user should not be asked to stop and hand-maintain `toolref`

### 5. Workflow

The skill must give the high-level workflow:

- literature grounding
- setup
- execution
- verification
- result interpretation

### 6. Scientific Norms

The skill must include the tool's key scientific quality checks:

- convergence
- validation
- model selection
- uncertainty or error reporting

### 7. Agent Behavior Rules

Short and operational.

For example:

- do not guess parameters from memory
- do not equate "job finished" with "scientifically valid"
- do not use user time to patch internal coverage gaps

## What A Tool Skill Must Not Contain

Do not turn a skill into:

- a second API manual
- a long option dump
- a version-specific syntax encyclopedia
- a maintenance checklist aimed at end users

Rule of thumb:

- if it is a parameter reference, it belongs in `toolref`
- if it is a scientific decision rule, it belongs in the skill
- if it is "what to do when docs are imperfect", it belongs in runtime protocol

## Runtime Contract

Every scientific CLI skill should be compatible with this user-facing contract:

1. The user asks for a scientific task in natural language
2. The agent decides whether a known scientific tool applies
3. The agent uses `toolref` first for interface certainty
4. If `toolref` is enough, continue normally
5. If `toolref` is incomplete, the agent falls back to official docs and keeps working
6. The user hears about the limitation only as context, not as a request for unpaid maintenance work

## Maturity Levels

The skill should be explicit about maturity.

Use one of:

- `toolref-first`: mature enough that `toolref` is the normal path
- `toolref-first, partial coverage`: good top-level coverage, deeper details may require fallback
- `toolchain-aware`: for multi-program ecosystems where the agent must first route to the correct sub-tool

## Golden Query Expectation

Once a tool becomes important, it should have a golden query checklist.

Minimum bar:

- at least three `show` queries that should directly hit the right page
- at least three `search` queries with realistic user phrasing
- at least one recovery case showing graceful fallback when coverage is weak

For toolchain ecosystems, at least one golden query should be task-oriented rather than tool-name-oriented.
Example shape:

- `read mapping nanopore`
- `variant calling vcf`
- `protein structure folding`

That is how end users actually ask.

## Production-Ready Bar

Do not confuse these concepts:

- page-complete
- parser-complete
- production-ready

For ScholarAIO, a scientific tool integration is production-ready when:

- the highest-value `show` queries directly hit
- the highest-value `search` queries usually rank the right page first
- refreshes do not silently reduce usable coverage
- the agent can keep serving the user even when some coverage is partial

This means:

- `production-ready` does not require mirroring every upstream page
- `manifest coverage complete` only means the curated entry set is complete
- the user experience matters more than theoretical documentation totality

## Manifest Guidance

When using manifest-based docs ingestion:

- prefer a curated set of high-value pages first
- add `fallback_urls` for flaky but important upstream pages
- preserve old cache when a forced refresh returns a worse result
- track fetched/expected/failed/restored counts in metadata
- if the user later needs broader coverage, evolve from curated manifest to discovery-based manifest instead of endlessly hand-editing page lists
- persist discovered manifests as local snapshots so later refreshes and completeness checks are deterministic
- reuse HTML fetched during discovery instead of downloading the same page twice
- allow discovery to reuse locally cached seed pages when upstream is temporarily unavailable
- for anchor-derived logical pages, allow refresh to reuse seed-page HTML by base URL, not only the exact fragment URL
- preserve or upgrade anchor metadata on curated high-value page names when upstream heading ids use a different canonical form

Good candidates for manifest-based onboarding:

- documentation portals with unstable navigation-heavy HTML
- multi-site toolchains where a small number of official pages matter far more than full-site crawl completeness

## Discovery-Based Expansion

When a tool outgrows a tiny curated manifest, use this upgrade path:

1. Start from official seed pages
2. Discover child pages or anchor sections automatically
3. Filter to the product's mainline scope
4. Snapshot the discovered manifest locally
5. Fetch/index from that snapshot with cache protection

This pattern is especially useful when:

- a docs portal has a reliable internal navigation structure
- a single large manual page contains many subcommands or sections
- the user wants "mainline docs as completely as possible" without dragging in plugins, extensions, or unrelated ecosystem noise

## Scope Discipline

Broader coverage still needs boundaries.

For example:

- OpenFOAM mainline docs can include fundamentals, tools, numerics, models, and post-processing while excluding plugins and secondary extensions
- Bioinformatics toolchains can include official subcommands and anchor-based sections of core manuals without trying to mirror the entire surrounding ecosystem

The agent should be explicit about this distinction:

- `mainline-complete enough` is a valid target
- `entire internet around the tool` is not

## Template

Use this shape when writing a new scientific CLI skill:

```md
# <Tool Name>

Short summary.

This skill stays lightweight:
- workflow
- scientific norms
- toolref-first behavior
- not a manual

## Agent Default Protocol

## Preconditions

## When To Use

## Toolref First

## Coverage Gaps / Fallback

## Core Workflow

## Scientific Norms

## Agent Behavior Rules
```

## Review Checklist

Before calling a new scientific skill "done", verify:

- it has an explicit agent default protocol
- it tells the agent not to push `toolref` maintenance onto users
- it distinguishes routing from interface reference
- it includes realistic `toolref` examples
- it states fallback behavior
- it does not read like a raw command manual

## Current Reference Implementations

Best current examples in this repo:

- `quantum-espresso`
- `lammps`
- `gromacs`

These show what "toolref-first" looks like after real onboarding and query hardening.
