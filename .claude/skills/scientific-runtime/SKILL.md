---
name: scientific-runtime
description: Shared runtime protocol for scientific CLI tasks. Use alongside tool-specific scientific skills so the agent knows how to route with toolref-first behavior, handle partial coverage, and avoid pushing maintenance work onto end users.
version: 1.0.0
author: ZimoLiao/scholaraio
license: MIT
tags: ["scientific-computing", "runtime-protocol", "toolref", "agent-behavior"]
---

# Scientific Runtime Protocol

This is a shared runtime skill for scientific CLI work.

It is not a tool manual.
It tells the agent how to behave when serving real users on scientific tool tasks.

Use it alongside a tool-specific scientific skill such as:

- `quantum-espresso`
- `lammps`
- `gromacs`
- `openfoam`
- `bioinformatics`

## Core Principle

ScholarAIO is for users, not for people who want to co-maintain the internal documentation layer.

So the agent should absorb complexity whenever possible.

The user should experience:

- natural language help
- reliable parameter lookup
- graceful fallback when coverage is partial

The user should not experience:

- being asked to manually patch `toolref`
- being forced to learn internal parser gaps
- being blocked because a documentation layer is imperfect

## Runtime Protocol

For any scientific CLI task:

1. Identify the scientific tool or sub-tool that matches the problem.
2. Use the tool-specific skill for workflow and scientific norms.
3. Use `toolref` first for commands, parameters, program pages, and option meanings.
4. If `toolref` is sufficient, continue normally.
5. If `toolref` is partial, fall back to official docs and continue the task.
6. Mention the coverage gap briefly only when it affects confidence or maintainability.
7. Do not turn the current user task into documentation maintenance work.

## Toolref-First Behavior

The agent should prefer:

- `scholaraio toolref show <tool> ...` for precise lookups
- `scholaraio toolref search <tool> "..."` for natural-language entry

Before writing configuration or scripts, first resolve:

- which program or subcommand is relevant
- which parameters are high-risk
- which defaults or restrictions matter for validity

## When Toolref Is Incomplete

If `toolref` does not fully answer the question:

- continue using the official documentation source
- clearly separate "task progress" from "maintenance opportunity"
- do not ask the user to stop and repair the docs layer first

Use this pattern:

- "I used `toolref` for the main entry point."
- "For this deeper detail, I fell back to the official docs because current coverage is partial."

## Escalation Rule

Escalate a gap to onboarding or maintenance only when:

- the same gap appears repeatedly
- it blocks a common task
- it affects correctness, not just convenience

If it is a one-off edge case, do not derail the user task.

## Separation Of Responsibilities

- tool-specific skill: when to use the tool, workflow, scientific norms
- `toolref`: interface and parameter reference
- scientific runtime: how to behave under uncertainty or partial coverage

## Anti-Patterns

Do not:

- dump raw flags from memory
- tell the user to "go improve toolref first"
- confuse a successful CLI run with a valid scientific result
- replace scientific judgment with parameter lookup alone

## Output Style

When answering the user:

- keep maintenance details short
- foreground scientific progress and decision-making
- mention fallback only when it materially changes confidence or provenance
