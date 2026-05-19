---
name: DeepDone Sync
slug: deepdone-sync
description: Reconstruct active work from the epic ledger, and from the roadmap when one exists, summarize true current state, identify drift, and set one exact next action. Use after interruption, handoff, or context loss. Trigger question: "Do I trust that my ledger matches reality?"
---

# DeepDone Sync

## Purpose

Recover fast from interruption without guessing.

This skill is for resuming:

- a single epic, or
- the active epic inside a multi-epic initiative

If the current work is a deliberate small task with no ledger, keep recovery compact and work from thread goal plus repo state.

## Input

Prefer explicit ledger path.
If none provided, locate work in this order:

1. explicit roadmap path from prompt, then use `Active Epic.ledger`
2. one roadmap with an obvious active epic
3. explicit epic ledger path from prompt
4. one obvious active epic ledger in `notes/epics/`
5. if no ledger exists, resume as a small task from thread goal and repo state

If multiple plausible roadmaps or epic ledgers exist and choice is unclear, surface ambiguity instead of guessing blindly.

## What To Read

### Epic ledger
Read the whole ledger, with special attention to:

- `Summary`
- `Constraints`
- `Milestones`
- `Decisions`
- `Verification Log`
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
2. If roadmap exists, confirm which epic is supposed to be active.
3. Summarize target outcome and current state.
4. Compare ledger claims against current diff and latest checks.
5. Identify the latest completed milestone.
6. Identify unresolved decisions, blockers, and stale status.
7. Confirm whether `Next Action` still makes sense.
8. If stale, rewrite `Next Action` to one concrete step.
9. Keep `Status` accurate.
10. If epic is complete and roadmap is waiting, recommend `DeepDone Advance` instead of more edits.

## Reconciliation Rules

- if code and ledger disagree, say so explicitly and reconcile before more edits
- if roadmap and ledger disagree on which epic is active, prefer the ledger that matches current code changes, but surface the mismatch clearly
- if an epic ledger says `complete` and roadmap `Active Epic.state` is `complete-pending-advance`, next action is usually `Run DeepDone Advance`
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
