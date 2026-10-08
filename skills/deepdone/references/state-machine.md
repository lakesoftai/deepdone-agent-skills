# DeepDone Workflow Contract

Read this reference before classifying or routing DeepDone work. This file is the authoritative lifecycle contract.

Invariant IDs are permanent. Do not rename or reuse them. When a rule is removed, move its block to `## Retired Invariants` and keep its ID.

## Active Invariants

### DD-STATE-001: Review pass owns completion

- Rule: Only a latest Review result of `pass` may make a task or epic `complete` or roadmap state `complete-pending-advance`.
- Applies to: `deepdone`, `phase-implement`, `phase-verify`, `phase-review`, `phase-advance`, `phase-sync`, `phase-commit`
- Evidence: Latest Review entry is `pass`, ledger Status is `complete`, and roadmap state is `complete-pending-advance` when a roadmap exists.

### DD-STATE-002: Changes invalidate review

- Rule: Any behavior-changing implementation or fixup after review appends a newer pending Review entry and routes through verification before review.
- Applies to: `deepdone`, `phase-implement`, `phase-fixup`, `phase-verify`, `phase-review`
- Evidence: Latest Review entry is `pending`, ledger remains active, and Next Action names verification.

### DD-REVIEW-001: Review captures exact Git snapshot

- Rule: A passing review of dirty work records compact reviewed scope, captures exact version-controlled state as a private Git review ref, and stores its object IDs in a local manifest.
- Applies to: `phase-review`, `phase-commit`, `phase-advance`, `phase-sync`
- Evidence: Latest passing Review contains review ID, base HEAD, manifest path, scope, and development-evidence roles; manifest resolves to one unchanged Git commit and tree under `refs/deepdone/reviews/`.

### DD-EVIDENCE-001: Development state is evidence, not commit ownership

- Rule: Selected task record or active epic ledger and optional epic roadmap are filesystem-hashed development evidence regardless of Git tracking or ignore state; they never become commit candidates merely because review depends on them.
- Applies to: `phase-review`, `phase-commit`, `phase-advance`, `phase-sync`
- Evidence: Schema-v2 manifest contains one `ledger` evidence record and optional `roadmap` record, while Git-reviewed paths are derived only from the private review snapshot.

### DD-COMMIT-001: Commit reproduces reviewed Git tree

- Rule: An actual commit may stage only Git-derived reviewed paths, every reviewed byte and mode must remain unchanged, and resulting commit tree must equal the reviewed tree.
- Applies to: `phase-review`, `phase-commit`
- Evidence: Temporary worktree projection, real-index tree, and resulting commit tree all equal manifest `review_tree`; committed paths equal Git diff from `base_head` to `review_ref`.

### DD-COMMIT-002: Unowned staged paths block commit

- Rule: Any staged path outside the reviewed change set blocks actual commit; unrelated unstaged and untracked paths remain untouched.
- Applies to: `phase-commit`
- Evidence: Candidate reports staged-unowned paths and actual commit refuses while any exist.

### DD-ADVANCE-001: Uncommitted or drifted reviewed work blocks advance

- Rule: A completed epic cannot advance until reviewed Git state is committed and clean and captured development evidence remains unchanged.
- Applies to: `deepdone`, `phase-advance`, `phase-sync`
- Evidence: Advance gate projects current HEAD over Git-derived reviewed paths, compares it with `review_tree`, checks dirty reviewed paths, and verifies evidence hashes.

### DD-DRIFT-001: Ambiguous ownership blocks

- Rule: Sync may repair mechanical state drift only when one work unit and its owned paths are clear; ambiguous ownership blocks.
- Applies to: `deepdone`, `phase-review`, `phase-sync`
- Evidence: Reconciliation names one work unit and exact scope, or records a blocker without modifying ambiguous work.

## Durable States

Epic ledger and compact task `## Status` values:

- `active`: implementation, verification, or review is still in progress
- `blocked`: user input or an external condition is required
- `complete`: latest implementation passed verification and review

Roadmap `Active Epic.state` values:

- `active`
- `blocked`
- `complete-pending-advance`
- `none`

Do not mark an epic `complete` or `complete-pending-advance` before latest review result is `pass`.

## Review Schema

New ledgers contain `## Review` after `## Verification Log`:

```md
## Review

- reviewed-at: 2026-07-11T12:00:00Z
  result: pass
  review-id: 20260711T120000Z-a1b2c3d4
  base-head: 0123456789abcdef0123456789abcdef01234567
  manifest: .deepdone/reviews/20260711T120000Z-a1b2c3d4.json
  scope:
    include:
      - src/
      - tests/
    exclude:
      - scratch/
  evidence:
    ledger: notes/epics/2026-07-11-example.md
    roadmap: notes/roadmap.md
  notes: no blocking findings
```

Allowed results: `pending`, `pass`, `fail`, `blocked`.

Latest entry wins. Missing `## Review` means `pending`. Add the section during review or sync when needed; do not require bulk migration.

Legacy passing entries and schema-v1 manifests remain readable. They may describe completed work, but they cannot authorize an actual commit. Advance may accept them only when the repository is already clean and applicable manifest identity and development evidence validate. Missing identity/evidence is ambiguous and blocks. Removed or damaged new-format contracts cannot use historical compatibility.

Markdown is the human review decision, compact scope declaration, and evidence-role record. It never lists every matched file.

Schema-v2 JSON is compact deterministic gate evidence. It stores:

- review ID, ledger path, and base HEAD
- private `review_ref`, synthetic `review_commit`, and `review_tree`
- changed-path count
- normalized include and exclude roots
- direct filesystem hashes for recognized evidence roles

It never stores a bulk path array. Git diff between `base_head` and `review_ref` is the exact path authority. Manifest schema version is `2`.

Any behavior-changing implementation or fixup after review makes the previous review stale. Route through verification and review again.

## Compact tasks

Apply the [task contract](task-contract.md) for shared selection, acceptance binding and the task lifecycle. A valid selected task is suitable durable state for intake and one task with known acceptance can enter Implement. Keep its selector pinned through Review completion. Completed tasks are excluded from new-run discovery. Tasks do not enter Advance or Archive; explicitly selected completed tasks report review completion separately from read-only committed/clean validation. These additions do not reorder general phase precedence.

## Supervisor States

- `no_state`
- `needs_intake`
- `needs_resume`
- `needs_advance_roadmap`
- `needs_tech_decision`
- `ready_to_implement`
- `needs_verification`
- `needs_review`
- `needs_review_fix`
- `ready_for_commit_candidate`
- `ready_to_commit`
- `ready_for_pr`
- `needs_ci_review`
- `ready_to_archive`
- `blocked_needs_user`
- `complete`

## Classification Precedence

Use first matching rule:

1. `blocked_needs_user`: STOP file, ambiguous active work, unexpected dirty files, missing acceptance, risky judgment, missing required authorization, or no safe progress.
2. `needs_intake`: non-trivial requirements exist and no suitable ledger exists.
3. `needs_resume`: one recoverable durable-state mismatch exists.
4. `needs_advance_roadmap`: user invoked advance, or a later supervisor run finds a reviewed complete epic with a committed clean review snapshot and unchanged evidence that must activate queued work or finalize roadmap completion.
5. `needs_tech_decision`: next milestone has an unresolved material or version-sensitive choice.
6. `ready_to_implement`: exactly one milestone is next with known acceptance and verification.
7. `needs_verification`: implement or fixup changed code. This transition is mandatory even when the phase ran fresh feedback checks; Verify may reuse only eligible current readiness receipts, never feedback promotion. See [verification contract](verification-contract.md).
8. `needs_review`: latest implementation is verified and latest review is absent, pending, or stale.
9. `needs_review_fix`: latest review is `fail` with accepted local findings.
10. `ready_for_commit_candidate`: user requested a candidate or mode is `until-commit-candidate`, and review passed.
11. `ready_to_commit`: user requested commit or mode is `until-commit` or `end-to-end`, and all gates pass.
12. `ready_for_pr`, `needs_ci_review`, or `ready_to_archive`: user explicitly requested that lifecycle action and its gates pass.
13. `complete`: no active or queued work and no blocking loop remains.

A classification describes repository state. It never grants authorization.

## Canonical Transitions

| Event | Required result |
|---|---|
| Plan phase handles non-trivial work | One active ledger, plus roadmap only for multi-epic work |
| Implement changes | Keep epic active; next state is verification |
| Verification passes | Keep epic active; next state is review |
| Verification fails | Stop, or allow one obvious local fix when mode permits |
| Review fails | Keep epic active; next state is review fix |
| Review fix changes code | Keep epic active; next state is verification |
| Review blocks | Mark epic and roadmap blocked; stop |
| Review passes | Mark epic complete and roadmap `complete-pending-advance` |
| Advance | Activate exactly one queued epic, or complete roadmap |
| Commit | Stop in `until-commit` and `end-to-end`; never auto-advance |

Commit remains optional as an integration action, but direct advance cannot cross uncommitted or drifted reviewed work. Commit the reviewed snapshot or explicitly abandon it before activating the next epic.

## Work Ownership

- Plan phase creates initial roadmap or ledger state.
- Implement phase writes code but never declares epic completion.
- Verify phase owns verification readiness.
- Review phase owns review result and epic completion.
- Fixup phase returns changed code to verification.
- Advance owns creation of the next epic ledger.
- Commit, PR, and Archive phases own only their named lifecycle actions.

## Drift Rules

Recover with sync when all are true:

- one intended roadmap or ledger is identifiable
- mismatch is stale status, stale Next Action, missing Review section, or verification recency
- current code and milestone still point to the same work unit

Block instead when any are true:

- multiple plausible active ledgers or roadmaps exist
- roadmap points to one epic while current changes clearly belong to another
- dirty-file ownership is unknown
- reconciling would require product, architecture, security, migration, or data-risk judgment

Clearly unrelated dirty files may coexist with active work only when active-scope ownership is provable. Review snapshot and commit must exclude and preserve them. Ignored ledger and roadmap are proven by direct hashes, not dirty-path membership.

## Retired Invariants

None.
