---
name: deepdone-plan
slug: deepdone-plan
description: Classify incoming work as a small task, a single epic, or a multi-epic initiative. Create only the minimum durable state needed to start execution cleanly. Use when starting non-trivial work, ingesting a requirements doc, or when task scope is still fuzzy.
---

# DeepDone Plan

## Purpose

Choose the correct execution unit before coding.

This skill must not force all non-trivial work into one epic.
Its first job is scope classification.

Possible outcomes:

1. **Small task**
   - no durable task file
   - move straight to implementation planning

2. **Single epic**
   - create exactly one epic ledger
   - plan 3 to 7 verifiable milestones

3. **Multi-epic initiative**
   - create one lightweight roadmap/index
   - create exactly one active epic ledger for the first epic only
   - do not pre-plan later epics in milestone detail

## Durable State Rules

Use the minimum file set needed.

### Small task
Create no task markdown files.

### Single epic
Create exactly one file:

`notes/epics/YYYY-MM-DD-<slug>.md`

### Multi-epic initiative
Create exactly two files:

- `notes/roadmap.md`
- `notes/epics/YYYY-MM-DD-<first-epic-slug>.md`

Do not create companion files like `plan.md`, `status.md`, `spec.md`, `research.md`, or `runbook.md` unless the user explicitly asks.

Do not create detailed epic ledgers for future epics.
Only the active epic gets milestone-level planning.

## Classification Rules

### Small task
Treat as a small task when most of these are true:

- single narrow code path
- no external research needed
- one clear acceptance check
- likely less than half day
- low interruption risk
- no meaningful sequencing beyond a few edits

### Single epic
Treat as a single epic when all or most are true:

- one main objective
- one main verification story
- can stay coherent in one thread and one worktree if needed
- 3 to 7 milestones fit naturally
- risks and unknowns can be handled inside one execution lane

### Multi-epic initiative
Treat as a multi-epic initiative when one or more are true:

- requirements doc, architecture doc, or PRD spans multiple product areas
- input already contains phases, tracks, or major delivery stages
- there are multiple independent verification stories
- user is creating a new app, service, or subsystem
- scaffolding, feature work, and hardening would otherwise be mixed into one plan
- a single epic would become vague, overloaded, or hard to resume

Important rule:
phases in a product or architecture document are **candidate containers**, not automatic epics.
Convert them into execution-sized epics only if they are truly implementable as one lane.

## Greenfield Rule

If repo or app scaffolding does not yet exist, do **not** assume the user must do that manually first.

Treat bootstrap work as:

- part of the first epic when it has real architectural decisions, or
- a small task only if it is trivial generator/setup work with one obvious acceptance check

## Roadmap Shape

For a multi-epic initiative, the roadmap file must stay tiny.
Use exactly these headings:

```md
# <Initiative title>

## Summary

## Constraints

## Cross-Cutting Decisions

## Epic Queue

## Active Epic

## Status
```

### Epic Queue Format

Use compact bullets like:

```md
- [-] bootstrap-shell
  - goal: create Flutter app shell, routing, base state, and local run/build loop
  - exit criteria: app boots, routing works, local verification commands exist
  - depends on: none
  - ledger: notes/epics/2026-04-14-bootstrap-shell.md

- [ ] archive-playback
  - goal: browse archive by date and play archive entries
  - exit criteria: archive list, detail view, playback, seek, happy-path smoke passes
  - depends on: bootstrap-shell
  - ledger: not-created
```

Status markers:

- `[ ]` queued
- `[-]` active
- `[x]` complete
- `[!]` blocked

Keep this file short.
No milestone breakdowns here.
No verification logs here.
No research dumps here.

### Cross-Cutting Decisions Format

Use only for choices that constrain multiple epics.

```md
- YYYY-MM-DD: state backend
  - scope: all app epics
  - chosen: use existing Redux store
  - reason: repo already standardizes on Redux middleware
  - source ledger: notes/epics/2026-04-14-bootstrap-shell.md
```

If there are no cross-cutting decisions yet, write `none`.

### Active Epic Format

Use exact fields:

```md
- name: bootstrap-shell
- ledger: notes/epics/2026-04-14-bootstrap-shell.md
- state: active
```

Allowed `state` values:

- `active`
- `blocked`
- `complete-pending-advance`
- `none`

## Epic Ledger Shape

For an active epic, use exactly these headings:

```md
# <Epic title>

## Summary

## Constraints

## Milestones

## Decisions

## Verification Log

Use structured result markers for every verification entry:

```md
- command: `just test api-auth`
  result: pass
  notes: focused auth test passed
- command: `uv run pytest tests/test_auth.py`
  result: fail
  notes: login fixture broken after schema change
- command: `just lint`
  result: blocked
  notes: no `justfile` in repo
```

Allowed `result` values:

- `pass`
- `fail`
- `blocked`

## Open Loops

## Next Action

## Status
```

## Milestone Rules

- milestones must be independently verifiable
- milestones must stay within one execution lane
- order must be explicit
- only one item can be next
- do not hide open questions inside milestone text
- each milestone should state touched areas, acceptance check, likely risks, and whether more research is needed
- include dependency notes when sequence is not obvious

Preferred format:

```md
- [ ] milestone name
  - touched areas: ...
  - acceptance: ...
  - risks: ...
  - research: none | specific unknown
  - depends on: ...
```

## Plan Mode Policy

Use your runtime's planning mode for this skill when available unless the task is obviously a small local task.
If no planning mode exists, write a compact plan and stop before creating durable state.
Focus planning on:
- scope classification
- whether this is small task, single epic, or multi-epic initiative
- milestone or epic boundaries
- verification strategy
- exact next action

## Workflow

1. Read the user request and any attached docs.
2. Restate goal and hard constraints from user plus repo context.
3. Classify as small task, single epic, or multi-epic initiative.
4. If small task:
   - say no ledger is needed
   - move straight to implementation planning
5. If single epic:
   - create one epic ledger
   - fill Summary, Constraints, Milestones, Next Action, Status
6. If multi-epic initiative:
   - create one roadmap file
   - derive a short epic queue from the source material
   - choose the smallest sensible first epic
   - create exactly one active epic ledger for that first epic
   - write that ledger path into both `Epic Queue` and `Active Epic`
   - do not create detailed plans for future epics
7. Put goal and non-goals into Summary.
8. Put real limits into Constraints.
9. Make the next action exact and singular.
10. Set Status:
   - roadmap: `active`
   - active epic: `active`

## Decomposition Guidance

When converting a large product doc into epics:

- prefer vertical execution lanes over vague phases
- split scaffolding from later feature breadth only if verification differs materially
- split offline/download concerns away from core playback unless they are trivial
- split platform-specific polish from MVP-critical cross-platform behavior
- keep later epics queued until earlier ones prove the architecture

## Output

Produce:

- scope verdict: small task | single epic | multi-epic initiative
- reason for the verdict
- if single epic: exact ledger path
- if multi-epic: exact roadmap path and first epic ledger path
- milestone list with acceptance checks for the active epic
- sequencing or dependency notes when needed
- exact next action

## Anti-Patterns

Do not:

- force a whole product doc into one epic
- mirror architecture-document phases blindly
- create more than one active epic ledger unless the user explicitly asks for parallel work
- create future-epic milestone plans prematurely
- create extra markdown bureaucracy
