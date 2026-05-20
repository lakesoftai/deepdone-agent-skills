---
name: deepdone-implement
slug: deepdone-implement
description: Execute only the next milestone from the active epic ledger, keep scope tight, and update progress, verification, open loops, and next action as you go. If the task is intentionally small and has no ledger, treat the thread goal as one compact milestone.
---

# DeepDone Implement

## Purpose

Implement one milestone, not the whole universe.

This skill is the execution engine for:

- a small task with no ledger, or
- the currently active epic in a single-epic or multi-epic workflow

It must not decompose product scope, invent future epics, or silently expand into adjacent work.

## Inputs

Prefer explicit ledger path.
If none provided, locate work in this order:

1. explicit active epic ledger from prompt
2. roadmap `Active Epic.ledger`
3. one obvious active epic ledger in `notes/epics/`
4. if no ledger exists, treat current thread goal as a small task

If multiple plausible active epic ledgers exist and the correct one is unclear, surface ambiguity instead of guessing.

## What To Read

### If epic-backed work
Read the whole epic ledger, with special attention to:

- `Summary`
- `Constraints`
- `Milestones`
- `Decisions`
- `Verification Log`
- `Open Loops`
- `Next Action`
- `Status`

If a roadmap exists, also read only:

- `Epic Queue`
- `Active Epic`
- `Status`

Use roadmap only to confirm scope and active-epic identity.
Do not treat the roadmap as a place to do implementation planning.

### If small task
Read the current thread goal, relevant AGENTS files, and current repo state.
Treat the whole task as one compact milestone.

## Preconditions

### Execution Gate

Before implementing, answer this gate explicitly. If any answer is not a clear yes, stop execution and switch to planning/reconciliation mode instead of coding:

- exactly one milestone or compact task is next
- files or surfaces to touch are obvious
- "done" means one observable acceptance result
- smallest useful verification command is obvious
- risk of spilling into the next milestone is low

If any answer is no or fuzzy, do not improvise. Record the ambiguity in `Open Loops` when a ledger exists, set `Next Action` to the exact planning or reconciliation step, and return the blocker.

### Epic-backed work
Before editing, confirm all are true:

- active epic ledger exists
- exactly one milestone is next, or `Next Action` points clearly into one milestone
- acceptance check for that milestone is known
- no unresolved blocker makes coding premature

If the current milestone explicitly lists `research: <specific unknown>` and the corresponding decision has not yet been made, stop and use `DeepDone Decide` before writing code.

### Small task
Before editing, confirm:

- goal is narrow
- one clear acceptance check exists
- no durable epic state is needed yet

If scope expands materially during execution, stop and hand back to `DeepDone Plan` instead of inventing ad hoc ledger state.

## Scope Rules

- touch only files needed for the current milestone or small task
- avoid opportunistic refactors unless they unblock current work directly
- do not start the next milestone in the same pass unless the user explicitly asks
- if scope expands, record it in `Open Loops` instead of silently swallowing more work
- if current milestone is app bootstrap or generator setup, scaffold directly within the milestone boundary

## Ledger Update Rules

Keep ledger current during milestone work:

- mark milestone progress in `Milestones`
- append material implementation decisions to `Decisions`
- append checks actually run to `Verification Log` with `command:`, `result: pass|fail|blocked`, and `notes:`
- add blocked checks or pending follow-ups to `Open Loops`
- update `Next Action` to one exact next step
- update `Status` when milestone or epic state changes

Do not create new sections.
Do not add status prose outside the ledger structure.

## Roadmap Interaction Rules

If the epic belongs to a multi-epic initiative and the current milestone completes the whole epic:

- mark the epic ledger `Status` as `complete`
- update the roadmap entry for this epic from `[-]` to `[x]`
- update roadmap `Active Epic.state` to `complete-pending-advance`
- do **not** create the next epic here
- set epic `Next Action` to `Run DeepDone Advance to activate the next queued epic.`

If the epic is blocked:

- mark epic `Status` as `blocked`
- if roadmap exists, update `Active Epic.state` to `blocked`
- put the blocker and unblock condition in `Open Loops`

## Plan Mode Policy

Do not switch to broad plan mode by default.
This skill assumes planning is already done.
Only re-plan if:
- current milestone is underspecified
- ledger and code disagree materially
- acceptance check is missing or invalid
- implementation reveals a blocking dependency that changes milestone boundaries

If re-planning is needed, stop execution, record the issue, and return a recommendation to use plan mode before further edits.

## Workflow

1. Locate the active work unit.
2. Restate the milestone boundary before editing.
3. Confirm acceptance check and stop conditions.
4. Implement only what the current milestone requires.
5. Run the smallest relevant checks first.
6. Record actual results in `Verification Log`.
7. Mark milestone done only if acceptance check passed, or explicitly mark blocked.
8. If more work remains in the epic, set one exact `Next Action` inside the next unfinished milestone.
9. If the epic is fully complete, update epic status and, if present, roadmap completion state.

## Done Rule

### Small task
Done only when:

- intended behavior exists
- required targeted checks were actually run or explicitly blocked
- no durable epic state is needed retroactively

### Epic-backed work
Milestone is done only when:

- intended behavior exists
- required targeted checks were actually run or explicitly blocked
- ledger reflects new truth

Epic is done only when:

- all milestones required for the epic are complete
- epic-level exit criteria are satisfied
- ledger `Status` is `complete`
- if roadmap exists, roadmap state is updated to `complete-pending-advance`

## Output

Return:

- work mode: small task | epic milestone
- exact ledger path if any
- milestone completed or blocked
- key files or surfaces touched
- checks run
- next action
