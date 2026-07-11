---
name: deepdone-orchestrate
slug: deepdone-orchestrate
description: Supervise DeepDone work from requirements intake through planning, implementation, verification, review, local commit, and explicit post-commit actions. Use when the user provides requirements, asks to continue existing DeepDone work, or requests a bounded automation mode.
---

# DeepDone Orchestrate

## Purpose

Inspect repository truth, classify current workflow state, invoke one narrow child skill at a time, and stop at the selected mode boundary or safety gate.

## Required References

Before classifying or routing, read:

- [Workflow contract](references/state-machine.md): states, precedence, transitions, review schema, ownership, and drift rules
- [Safety and modes](references/safety-and-modes.md): mode stop targets, authorization provenance, hard stops, and dirty-work rules

Treat those references as authoritative. Do not reconstruct their tables from memory.

## Inputs

Accept:

- requirements or continuation goal
- mode
- explicit roadmap or ledger path
- constraints, non-goals, approvals, and stop conditions

Default mode: `one-step`.

Commit modes: `until-commit` and `end-to-end`. They authorize local commit only and stop after commit.

## Child Skills

Invoke only:

- `$deepdone-plan`
- `$deepdone-sync`
- `$deepdone-advance`
- `$deepdone-decide`
- `$deepdone-implement`
- `$deepdone-verify`
- `$deepdone-review`
- `$deepdone-fixup`
- `$deepdone-commit`
- `$deepdone-pr`
- `$deepdone-archive`

Stop if the required child skill is unavailable.

## Inspection Order

Inspect:

1. latest user instruction and selected mode
2. `.deepdone/STOP`
3. `git status --short --untracked-files=all`
4. current branch, staged diff, unstaged diff, and relevant untracked files
5. root and nested `AGENTS.md`
6. explicit roadmap or ledger path
7. `notes/roadmap.md` and its active ledger
8. one obvious active ledger when no roadmap selects one
9. milestones, Verification Log, Review, Open Loops, Next Action, and Status
10. current repository files and latest check evidence

Use `scripts/inspect_deepdone_state.py` when available for stable signals. Verify its output against source files before acting.

## Workflow

1. Read both required references.
2. Inspect repository state in the stated order.
3. Resolve current-run authorizations from the exact user request and selected mode.
4. Classify state using workflow-contract precedence.
5. Choose the single child skill mapped to that state.
6. Invoke it with a narrow boundary and explicit authorization block.
7. Inspect its output, changed files, ledger, roadmap, and checks.
8. Reclassify from repository truth.
9. Stop when mode target or safety condition is reached.
10. Continue only when mode permits another transition and new evidence exists.

`one-step` performs exactly one child transition.

`until-epic` stops after review passes. It does not commit.

`until-commit` and `end-to-end` stop after local commit. They do not advance, push, create a PR, archive, merge, or deploy.

## Child Invocation Contract

Provide:

```text
Use $<skill-name>.

Supervisor context:
- Requirements: <goal>
- Mode: <mode>
- Classification before: <state>
- Roadmap: <path or none>
- Active ledger: <path or none>
- Boundary: perform only this transition.

Authorizations:
- commit: allowed|denied; source: exact user request|mode|none
- pr-create: allowed|denied; source: exact user request|none
- archive: allowed|denied; source: exact user request|none
- push: allowed|denied; source: exact user request|none

Stop on ambiguity, scope expansion, failed verification beyond one allowed local fix, risky review judgment, or missing authority.
```

Never use a classification label as authorization.

## Progress Rules

Continue only when:

- repository state changed or new evidence appeared
- next transition is clear
- selected mode includes that transition
- child remained inside scope
- no hard stop applies

Allow at most one automatic verification fix and one automatic review-fix cycle per run.

Do not invoke the same child twice for the same unchanged reason.

## Durable State

Child skills own normal roadmap and ledger edits.

Supervisor may update existing durable state only to record a stop reason or reconcile metadata directly required for routing. Do not create duplicate ledgers or future epic ledgers.

## Failure Handling

After child failure:

1. inspect git status and changed files
2. inspect roadmap and ledger truth
3. use `$deepdone-sync` only for recoverable drift defined by the workflow contract
4. otherwise stop with exact blocker and next safe action

After verification failure, allow one obvious local fix only when current mode permits it. Otherwise stop.

After review failure, use `$deepdone-fixup` only for accepted local low-risk findings. Stop for judgment calls.

## Output

Return:

- inspected state
- classification before
- child skill invoked, if any
- result and checks
- changed files
- classification after
- stop reason or exact next action
