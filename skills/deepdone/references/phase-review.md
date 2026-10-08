# Review Phase

For a selected compact task, apply the [task contract](task-contract.md) and carry its explicit `--task` selector through every helper. Epic-only roadmap/milestone rules below do not apply to tasks.

## Purpose

Review local diff skeptically, with correctness above agreement.

## Conforms To

- `DD-STATE-001`, `DD-STATE-002`
- `DD-OWN-001`, `DD-DRIFT-001`
- `DD-REVIEW-001`, `DD-EVIDENCE-001`, `DD-COMMIT-001`

## Reviewer context and independence

Use one fresh reviewer context when the host provides it. Supply original requirements, acceptance and constraints; selected task/epic and slice; the exact active diff including relevant untracked files; necessary surrounding source; and actual check definitions, results, purposes, freshness and known limitations. Identify the observed source with existing observation/snapshot facilities. Do not pass only the implementer's summary or verdict.

Before recording pass and capturing the snapshot, recheck that source and verification still apply to what the reviewer saw. Changed source needs applicable verification and review again. No new durable review protocol is required.

If a separate context is unavailable, disclose that limitation and use bounded self-review. Never claim independence. An explicit user requirement for independent review still applies; do not provision another service to satisfy it.

Review both missing requirements and implementation correctness. Inspect changed assertions, fixtures, test selection, CI gates, coverage/performance budgets and suppressions for lost checking. A justified replacement is valid. Findings need concrete evidence, impact and a useful correction direction. A clean review is valid; require neither a finding quota nor speculative hardening, routine specialists or automatic mutation testing. Use an isolated targeted mutation only to resolve a concrete doubt about a critical check.

The supervisor adjudicates advice: accept supported findings, reject incorrect recommendations with a reason, and preserve correct behavior. Reviewer advice alone is neither product authority nor a reason to patch correct code. Keep material blockers ahead of minor follow-ups and stop reviewing when acceptance is met.

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

Review only active-scope changes. Clearly unrelated files may remain dirty when active-scope ownership is provable; inspect enough to confirm exclusion, then leave them untouched. Stop if ownership is ambiguous. If no local changes exist but the milestone claims implementation in commits, require an explicit review base instead of guessing.

## Ledger Writeback

For the selected durable work record:

- ensure `## Review` exists after `## Verification Log`
- append one entry with `reviewed-at`, `result`, and `notes`; latest entry wins
- keep accepted findings or unresolved questions in `Open Loops`
- note residual risks plainly

Set review `result` as:

- `pass`: no blocking or strong unresolved findings
- `fail`: review found local defects that should be fixed before commit
- `blocked`: review found product, architecture, security, migration, or prioritization judgment that needs user input

On `pass`:

- create a stable `review-id` from UTC timestamp plus eight random hexadecimal characters
- record current full `base-head`
- record manifest path `.deepdone/reviews/<review-id>.json`
- record compact `scope.include` roots that cover active Git work
- record narrow `scope.exclude` roots for distinguishable unrelated work inside an included root
- record active ledger under `evidence.ledger`
- for an epic, record its associated `notes/roadmap.md` under `evidence.roadmap`; tasks must omit it
- for a task or final epic pass with every supported top-level milestone explicitly complete, mark ledger `Status` as `complete`; for a final epic with roadmap change its queue item to `[x]` and `Active Epic.state` to `complete-pending-advance`
- for an intermediate epic pass, keep ledger and roadmap active, capture the genuine snapshot after evidence writes, and route to the next eligible milestone only after this slice has crossed Verify and Review
- never demote required regression checks or rewrite receipts to make an intermediate slice pass
- set `Next Action` from supervisor mode: for `until-epic`, await commit or explicit abandonment before advance when a roadmap has queued or finalization work, otherwise await the next explicit workflow request; use commit for commit-authorized modes and candidate for candidate mode
- after all ledger and roadmap writes, run bundled `scripts/capture_reviewed_change_set.py` with the exact ledger path
- treat pass as actionable only when capture succeeds; on capture failure append a newer `pending` or `blocked` Review entry with the exact failure

Use this passing entry shape:

```md
- reviewed-at: <timestamp>
  result: pass
  review-id: <stable-id>
  base-head: <full-sha>
  manifest: .deepdone/reviews/<review-id>.json
  scope:
    include:
      - <repo-relative-file-or-directory>
    exclude:
      - <unrelated-file-or-directory>
  evidence:
    ledger: <repo-relative-ledger-path>
    roadmap: notes/roadmap.md
  notes: <summary>
```

Omit `evidence.roadmap` for every task and when no epic roadmap exists. Keep scope compact. Prefer a few narrow directories or exact files over one entry per changed path. Never make the agent enumerate thousands of files.

Markdown is authoritative for review result, compact scope, and evidence roles. Capture helper expands that scope against current Git state, excludes evidence paths from commit ownership, builds a temporary index from `base-head`, writes one reviewed tree, creates one synthetic commit, and stores it under `refs/deepdone/reviews/<review-id>`.

Schema-v2 JSON is ignored local gate evidence, never run logging. It stores Git object IDs, changed-path count, normalized scope, and direct hashes for active ledger and optional roadmap. It contains no bulk path list. Do not edit ledger or roadmap after capture; any later change invalidates evidence and requires a new review capture.

On `fail`, keep epic and roadmap active and set `Next Action` to run the Fixup phase through `$deepdone`.

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

1. Read full review scope and the [verification contract](verification-contract.md). Validate every pinned reference and latest required readiness attempt. Judge inventory sufficiency, declared context, and exclusions.
2. Check whether implementation matches stated milestone.
3. Look for behavior regressions and hidden coupling.
4. Inspect auth, data, config, and migration surfaces with extra skepticism.
5. Check whether tests prove intended behavior.
6. Classify each finding by severity.
7. Append structured Review entry and update lifecycle state.
8. On pass, capture exact reviewed Git snapshot and development evidence with bundled helper. Capture rejects stale receipts, broken artifact chains, or relevant dirty inputs outside reviewed ownership.
9. Report findings first.

## Output

Return:

- findings ordered by severity
- open questions or assumptions
- brief integration readiness statement
