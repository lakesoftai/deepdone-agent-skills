# Implement Phase

## Conforms To

- `DD-STATE-001`, `DD-STATE-002`

## Purpose

Implement one selected task or epic milestone.

This internal phase is the execution engine for:

- a small task with a compact task record, or
- the currently active epic in a single-epic or multi-epic workflow

It must not decompose product scope, invent future epics, or silently expand into adjacent work.

## Inputs

Use shared [work-unit selection](task-contract.md#selection). Pin `--task` or `--ledger` across phases. Missing durable state requires Plan; ambiguous ownership blocks.

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
Read the selected task record, relevant AGENTS files and repo state. Use its goal, scope, acceptance/check pairs and constraints without inventing a milestone.

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

If the current milestone explicitly lists `research: <specific unknown>` and the corresponding decision has not yet been made, stop and route through the Decide phase before writing code.

### Small task
Before editing, confirm:

- goal is narrow
- one clear acceptance check exists
- a valid compact task record is selected

If scope expands materially during execution, stop and route through the Plan phase instead of inventing ad hoc ledger state.

## Scope Rules

- touch only files needed for the current milestone or small task
- avoid opportunistic refactors unless they unblock current work directly
- do not start the next milestone in the same pass unless the user explicitly asks
- if scope expands, record it in `Open Loops` instead of silently swallowing more work
- if current milestone is app bootstrap or generator setup, scaffold directly within the milestone boundary

## Ledger Update Rules

For compact tasks follow [task lifecycle](task-contract.md#lifecycle): keep active, append pending Review after changes, use existing sections and never edit a roadmap. The following milestone rules apply to epics.

Keep ledger current during milestone work:

- mark milestone progress in `Milestones`
- append material implementation decisions to `Decisions`
- append checks actually run to `Verification Log` with `command:`, `result: pass|fail|blocked`, and `notes:`
- add blocked checks or pending follow-ups to `Open Loops`
- update `Next Action` to one exact next step
- update `Status` when milestone or epic state changes
- when behavior changes after any prior review, append a `## Review` entry with `reviewed-at: not-run`, `result: pending`, and notes that code changed

Do not create new sections.
Do not add status prose outside the ledger structure.

## Roadmap Interaction Rules

If the current milestone finishes all planned implementation work:

- keep epic ledger `Status` as `active`
- keep roadmap entry and `Active Epic.state` as `active`
- set `Next Action` to run the Verify phase through `$deepdone`
- do not mark the epic complete or advanceable

Only the Review phase may mark an epic `complete` and roadmap state `complete-pending-advance` after a passing review.

If the epic is blocked:

- mark epic `Status` as `blocked`
- if roadmap exists, update `Active Epic.state` to `blocked`
- put the blocker and unblock condition in `Open Loops`

## Plan Mode Policy

Do not switch to broad plan mode by default.
This phase assumes planning is already done.
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
7. Mark implementation milestone done only if its implementation acceptance check passed, or explicitly mark blocked.
8. If more work remains in the epic, set one exact `Next Action` inside the next unfinished milestone.
9. If implementation work is finished, keep epic active and route to verification.

Checks run here are implementation feedback, not the workflow verification gate. Route to the Verify phase after code changes even when these checks pass. Use purpose `feedback` for captured implementation checks. Verify requires an actual `readiness` execution; feedback cannot be promoted. See [verification contract](verification-contract.md).

## Done Rule

### Small task
Done only when:

- intended behavior exists
- required targeted checks were actually run or explicitly blocked
- the task record reflects implementation truth and remains active for verification/review

### Epic-backed work
Milestone is done only when:

- intended behavior exists
- required targeted checks were actually run or explicitly blocked
- ledger reflects new truth

This phase never declares an epic done. Verification and review remain required even when all implementation milestones are checked.

## Output

Return:

- work mode: small task | epic milestone
- exact ledger path if any
- milestone completed or blocked
- key files or surfaces touched
- checks run
- next action
