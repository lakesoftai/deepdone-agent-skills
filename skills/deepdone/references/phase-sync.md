# Sync Phase

## Purpose

Recover fast from interruption without guessing.

## Conforms To

- `DD-STATE-001`, `DD-REVIEW-001`, `DD-EVIDENCE-001`
- `DD-OWN-001`, `DD-ADVANCE-001`, `DD-DRIFT-001`

This internal phase is for resuming:

- a single epic, or
- the active epic inside a multi-epic initiative

For compact tasks, read the pinned task record and [task contract](task-contract.md). Completed tasks require explicit selection; never reopen them during discovery.

## Input

Use shared work-unit selection. Preserve the explicit `--task` or `--ledger` selector throughout the run; conflicting candidates or broken pointers block.

## What To Read

### Epic ledger
Read the whole ledger, with special attention to:

- `Summary`
- `Constraints`
- `Milestones`
- `Decisions`
- `Verification Log`
- `Review`, treating a missing section as `pending`
- `Open Loops`
- `Next Action`
- `Status`

### Roadmap, if present
Read only:

- `Epic Queue`
- `Cross-Cutting Decisions`
- `Active Epic`
- `Status`

### Current reality
Also compare ledger against current reality when available:

- current git diff
- current branch or worktree state
- latest verification outputs
- files or commands changed after the last ledger update

## Resume Output

Produce compact state:

- work mode
- roadmap path if any
- exact epic ledger path if any
- goal
- current milestone or current task step
- milestones done
- blockers or open loops
- latest verification truth
- latest review truth
- drift or stale-state warnings
- exact next action

## Plan Mode Policy

Use normal execution mode if ledger, code, and checks are aligned.
Escalate to your runtime's planning mode when available if:
- ledger state is stale
- next action is no longer valid
- milestone boundaries need revision
- resumed work must be resequenced
If no planning mode exists, write a compact reconciliation plan and stop before edits.

## Workflow

1. Locate the active work unit.
2. For an epic, confirm its associated roadmap. A task has no roadmap association.
3. Summarize target outcome and current state.
4. Compare ledger claims against current diff and latest checks.
5. Identify the latest completed milestone.
6. Identify unresolved decisions, blockers, and stale status.
7. Treat a missing Review section as pending; add it only when reconciliation needs durable review state.
8. Confirm whether `Next Action` still makes sense.
9. If stale, rewrite `Next Action` to one concrete step.
10. Keep `Status` accurate.
11. Recommend `Requested phase: advance` through `$deepdone` only when epic is complete, latest review result is `pass`, and reviewed Git snapshot plus development evidence pass the advance gate.

## Reconciliation Rules

- reconcile only stale status, stale Next Action, missing Review, or verification recency when one work unit is unambiguous
- block on multiple plausible active ledgers, current changes belonging to another epic, unrelated dirty files, or judgment-heavy mismatch
- if an epic ledger says `complete` and roadmap `Active Epic.state` is `complete-pending-advance`, next action is commit or explicit abandonment while reviewed Git state is uncommitted or drifted; otherwise use `Run DeepDone with Requested phase: advance`
- if an epic says complete without latest review result `pass`, reopen it as active and route to review
- if no meaningful changes exist beyond the ledger, preserve finished milestones and do not reopen them casually
- if a milestone was partially implemented but not verified, keep it in progress or reopen it explicitly

## Guardrails

- do not create a second ledger for the same epic
- do not invent progress not present in the file or code
- do not auto-advance roadmap here
- do not restart planning from scratch unless the existing ledger is obviously unusable

## Output

Return:

- work mode
- exact roadmap path if any
- exact ledger path if any
- state summary
- drift or mismatch notes
- next action

## Bounded progress resolution

For ambiguous implementation stage, inspect selected requirements, source/diff, milestones and complete evidence, then return a token-bound transient progress resolution (see state-machine.md), or the precise missing fact. Do not ask the user for repository-answerable facts. Preserve earlier outcomes and their consumed budgets. Receipt/Review bookkeeping alone does not require another Sync. Never repeat unchanged Sync without a resolution or blocker.
