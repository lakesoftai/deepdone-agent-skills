---
name: deepdone
description: Run DeepDone as one bounded software workflow from requirements intake through planning, implementation, verification, review, local commit, and explicit post-commit actions. Use when the user provides requirements, asks to continue existing DeepDone work, or requests a bounded automation mode.
license: Apache-2.0
compatibility: Requires Git, Python 3.10+, a writable Git worktree, and command execution.
metadata:
  author: lakesoftai
---

# DeepDone

## Purpose

Inspect repository truth, classify current workflow state, execute one narrow internal phase at a time, and stop at the selected mode boundary or safety gate.

## Conforms To

- `DD-STATE-001`, `DD-STATE-002`
- `DD-MODE-001`, `DD-MODE-002`
- `DD-AUTH-001`, `DD-AUTH-002`
- `DD-OWN-001`, `DD-ADVANCE-001`, `DD-DRIFT-001`

## Required References

Before classifying or routing, read:

- [Workflow contract](references/state-machine.md): states, precedence, transitions, review schema, ownership, and drift rules
- [Safety and modes](references/safety-and-modes.md): mode stop targets, authorization provenance, hard stops, and dirty-work rules

Treat those references as authoritative. Do not reconstruct their tables from memory.

After classification, read exactly one routed phase reference. Do not preload unrelated phases.

## Inputs

Accept:

- requirements or continuation goal
- mode
- optional requested phase
- explicit roadmap or ledger path
- constraints, non-goals, approvals, and stop conditions

Default mode: `one-step`.

Commit modes: `until-commit` and `end-to-end`. They authorize local commit only and stop after commit.

A requested phase is a routing preference, not a state or authorization override. If it does not match the required transition, report the required phase and stop unless the selected loop mode independently permits that transition.

## Phase Routing

Map the first matching workflow classification to exactly one action:

| Classification | Action |
|---|---|
| `needs_intake` | Read and execute [Plan phase](references/phase-plan.md) |
| `needs_resume` | Read and execute [Sync phase](references/phase-sync.md) |
| `needs_advance_roadmap` | Read and execute [Advance phase](references/phase-advance.md) |
| `needs_tech_decision` | Read and execute [Decide phase](references/phase-decide.md) |
| `ready_to_implement` | Read and execute [Implement phase](references/phase-implement.md) |
| `needs_verification` | Read and execute [Verify phase](references/phase-verify.md) |
| `needs_review` | Read and execute [Review phase](references/phase-review.md) |
| `needs_review_fix` | Read and execute [Fixup phase](references/phase-fixup.md) |
| `ready_for_commit_candidate`, `ready_to_commit` | Read and execute [Commit phase](references/phase-commit.md) |
| `ready_for_pr`, `needs_ci_review` | Read and execute [PR phase](references/phase-pr.md) |
| `ready_to_archive` | Read and execute [Archive phase](references/phase-archive.md) |
| `blocked_needs_user`, `complete` | Execute no phase; report state and stop |

Stop if the required phase reference is unavailable.

## Inspection Order

Inspect:

1. latest user instruction, requested phase, and selected mode
2. `.deepdone/STOP`
3. `git status --short --untracked-files=all`
4. current branch, staged diff, unstaged diff, and relevant untracked files
5. root and nested `AGENTS.md`
6. explicit roadmap or ledger path
7. `notes/roadmap.md` and its active ledger
8. one obvious active ledger when no roadmap selects one
9. milestones, Verification Log, Review, reviewed change-set manifest and private review ref, Open Loops, Next Action, and Status
10. current repository files and latest check evidence

Use `scripts/inspect_deepdone_state.py` when available for stable signals. Verify its output against source files before acting.

## Workflow

1. Read both required references.
2. Inspect repository state in the stated order.
3. Resolve current-run authorizations from the exact user request and selected mode.
4. Classify state using workflow-contract precedence.
5. Validate any requested phase against that classification.
6. Choose the single phase mapped to that state.
7. Read only that phase reference and execute it with the phase contract below.
8. Inspect changed files, ledger, roadmap, and checks.
9. Reclassify from repository truth.
10. Stop when mode target or safety condition is reached.
11. Continue only when mode permits another transition and new evidence exists.

`one-step` performs exactly one phase transition.

`until-epic` stops after review passes. It does not commit.

`until-commit` and `end-to-end` stop after local commit. They do not advance, push, create a PR, archive, merge, or deploy.

## Phase Execution Contract

Before executing a phase, bind this context:

```text
Phase context:
- Requirements: <goal>
- Mode: <mode>
- Phase: <phase-name>
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
- phase remained inside scope
- no hard stop applies

Before routing to Advance, require bundled gate to prove latest reviewed Git snapshot is committed and clean and captured ledger or roadmap evidence is unchanged.

Allow at most one automatic verification fix and one automatic review-fix cycle per run.

Do not execute the same phase twice for the same unchanged reason.

## Durable State

The routed phase owns normal roadmap and ledger edits defined by its reference.

Supervisor routing may update existing durable state only to record a stop reason or reconcile metadata directly required for routing. Do not create duplicate ledgers or future epic ledgers.

## Failure Handling

After phase failure:

1. inspect git status and changed files
2. inspect roadmap and ledger truth
3. execute the Sync phase only for recoverable drift defined by the workflow contract
4. otherwise stop with exact blocker and next safe action

After verification failure, allow one obvious local fix only when current mode permits it. Otherwise stop.

After review failure, execute the Fixup phase only for accepted local low-risk findings. Stop for judgment calls.

## Output

Return:

- inspected state
- classification before
- phase executed, if any
- result and checks
- changed files
- classification after
- stop reason or exact next action
