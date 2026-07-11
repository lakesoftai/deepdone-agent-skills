---
name: deepdone-review
slug: deepdone-review
description: Perform skeptical local code review focused on correctness, regressions, security, overscope, and missing tests, then record findings and residual risk. Use before final integration or handoff.
---

# DeepDone Review

## Purpose

Review local diff like hostile teammate who wants truth.

## Primary Review Axes

- correctness
- regressions
- security and permissions
- overscoped changes
- missing or weak tests
- rollback pain

## Severity Rubric

Use these labels:

- `block`: must fix before integration. Includes correctness break, security exposure, data loss risk, broken migration, failing required check, or behavior that contradicts the milestone.
- `strong-concern`: likely should fix before commit, but may need user prioritization. Includes brittle design, weak verification on risky paths, broad coupling, or hidden rollback cost.
- `nit`: small local cleanup that does not change safety or correctness.

Do not inflate style issues into blockers.
Do not bury real blockers as nits.

## Review Behavior

- findings first
- severity order
- cite exact files and lines when possible
- no praise padding
- if no findings, say so plainly and call out remaining test gaps or uncertainty
- include clear fix direction for each actionable finding
- separate product or architecture questions from code findings

## Review Scope

Inspect the complete local change set before issuing a result:

- `git status --short --untracked-files=all`
- unstaged diff
- staged diff
- contents of relevant untracked files
- active milestone, constraints, verification evidence, and AGENTS instructions

Review only active-scope changes. Stop if unrelated dirty files make ownership unclear. If no local changes exist but the milestone claims implementation in commits, require an explicit review base instead of guessing.

## Ledger Writeback

When epic ledger exists:

- ensure `## Review` exists after `## Verification Log`
- append one entry with `reviewed-at`, `result`, and `notes`; latest entry wins
- keep accepted findings or unresolved questions in `Open Loops`
- note residual risks plainly

Set review `result` as:

- `pass`: no blocking or strong unresolved findings
- `fail`: review found local defects that should be fixed before commit
- `blocked`: review found product, architecture, security, migration, or prioritization judgment that needs user input

On `pass`:

- mark ledger `Status` as `complete`
- if roadmap exists, change current queue item from `[-]` to `[x]`
- set roadmap `Active Epic.state` to `complete-pending-advance`
- set `Next Action` from supervisor mode: for `until-epic`, advance only when a roadmap has queued or finalization work, otherwise await the next explicit workflow request; use commit for commit-authorized modes and candidate for candidate mode

On `fail`, keep epic and roadmap active and set `Next Action` to `$deepdone-fixup`.

On `blocked`, mark epic and roadmap blocked and state exact unblock condition.

## Surface Checklists

### Auth And Permissions

- caller identity is verified at the correct boundary
- authorization checks happen before data access or mutation
- failures do not leak sensitive internal state
- tests include allowed and denied paths

### Schema And Migrations

- migration is reversible or rollback pain is explicit
- reads and writes work across expected old and new shapes
- nullable, default, and backfill behavior is deliberate
- migration ordering is safe for deploy reality

### Config And Deployment

- defaults are safe
- secrets are not hardcoded or logged
- environment-specific behavior is explicit
- generated or local-only files are not included

### Public API Or User-Facing Behavior

- response shape, status code, event name, or UI state matches contract
- error cases are covered, not only happy path
- compatibility impact is stated
- tests prove the user-visible acceptance condition

### Shared Libraries

- callers outside the milestone still satisfy the new contract
- behavior changes are named in tests or docs
- narrow fix did not become broad refactor

## Workflow

1. Read full review scope and recent verification results.
2. Check whether implementation matches stated milestone.
3. Look for behavior regressions and hidden coupling.
4. Inspect auth, data, config, and migration surfaces with extra skepticism.
5. Check whether tests prove intended behavior.
6. Classify each finding by severity.
7. Append structured Review entry and update lifecycle state.
8. Report findings first.

## Output

Return:

- findings ordered by severity
- open questions or assumptions
- brief integration readiness statement
