# DeepDone Workflow Contract

Read this reference before classifying or routing DeepDone work. This file is the authoritative lifecycle contract.

Invariant IDs are permanent. Do not rename or reuse them. When a rule is removed, move its block to `## Retired Invariants` and keep its ID.

## Active Invariants

### DD-STATE-001: Review pass owns completion

- Rule: Only a latest Review result of `pass` may make an epic `complete` or roadmap state `complete-pending-advance`.
- Applies to: `deepdone-orchestrate`, `deepdone-implement`, `deepdone-verify`, `deepdone-review`, `deepdone-advance`, `deepdone-sync`, `deepdone-commit`
- Evidence: Latest Review entry is `pass`, ledger Status is `complete`, and roadmap state is `complete-pending-advance` when a roadmap exists.

### DD-STATE-002: Changes invalidate review

- Rule: Any behavior-changing implementation or fixup after review appends a newer pending Review entry and routes through verification before review.
- Applies to: `deepdone-orchestrate`, `deepdone-implement`, `deepdone-fixup`, `deepdone-verify`, `deepdone-review`
- Evidence: Latest Review entry is `pending`, ledger remains active, and Next Action names verification.

### DD-REVIEW-001: Review identifies exact paths

- Rule: A passing review of dirty work records one exact reviewed change set with review ID, base HEAD, local manifest path, and repository-relative paths.
- Applies to: `deepdone-review`, `deepdone-commit`, `deepdone-advance`, `deepdone-sync`
- Evidence: Latest passing Review entry contains all required change-set fields and its manifest validates against current repository state.

### DD-COMMIT-001: Commit contains only reviewed unchanged paths

- Rule: An actual commit may stage and commit only paths in the latest reviewed change set, and every path must be unchanged since capture.
- Applies to: `deepdone-review`, `deepdone-commit`
- Evidence: Pre-commit cached paths and resulting commit paths exactly equal the manifest path set.

### DD-COMMIT-002: Unowned staged paths block commit

- Rule: Any staged path outside the reviewed change set blocks actual commit; unrelated unstaged and untracked paths remain untouched.
- Applies to: `deepdone-commit`
- Evidence: Candidate reports staged-unowned paths and actual commit refuses while any exist.

### DD-ADVANCE-001: Dirty reviewed work blocks advance

- Rule: A completed epic cannot advance while any path in its latest reviewed change set remains dirty.
- Applies to: `deepdone-orchestrate`, `deepdone-advance`, `deepdone-sync`
- Evidence: Advance stops with exact dirty reviewed paths until they are committed or explicitly abandoned outside DeepDone.

### DD-DRIFT-001: Ambiguous ownership blocks

- Rule: Sync may repair mechanical state drift only when one work unit and its owned paths are clear; ambiguous ownership blocks.
- Applies to: `deepdone-orchestrate`, `deepdone-review`, `deepdone-sync`
- Evidence: Reconciliation names one work unit and exact scope, or records a blocker without modifying ambiguous work.

## Durable States

Epic ledger `## Status` values:

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
  paths:
    - src/example.py
    - notes/epics/2026-07-11-example.md
  notes: no blocking findings
```

Allowed results: `pending`, `pass`, `fail`, `blocked`.

Latest entry wins. Missing `## Review` means `pending`. Add the section during review or sync when needed; do not require bulk migration.

Legacy passing entries without change-set fields remain readable. They may describe completed work, but they cannot authorize actual commit of dirty work until review runs again and captures a manifest.

The Markdown entry is the agent contract and human-readable path record. The ignored JSON manifest is deterministic gate evidence only. Manifest schema version is `1`.

Any behavior-changing implementation or fixup after review makes the previous review stale. Route through verification and review again.

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
4. `needs_advance_roadmap`: user invoked advance, or a later supervisor run finds a reviewed complete epic with a clean reviewed path set that must activate queued work or finalize roadmap completion.
5. `needs_tech_decision`: next milestone has an unresolved material or version-sensitive choice.
6. `ready_to_implement`: exactly one milestone is next with known acceptance and verification.
7. `needs_verification`: implement or fixup changed code. This transition is mandatory even when the child ran fresh feedback checks; verify may reuse complete current evidence.
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
| Plan non-trivial work | One active ledger, plus roadmap only for multi-epic work |
| Implement changes | Keep epic active; next state is verification |
| Verification passes | Keep epic active; next state is review |
| Verification fails | Stop, or allow one obvious local fix when mode permits |
| Review fails | Keep epic active; next state is review fix |
| Review fix changes code | Keep epic active; next state is verification |
| Review blocks | Mark epic and roadmap blocked; stop |
| Review passes | Mark epic complete and roadmap `complete-pending-advance` |
| Advance | Activate exactly one queued epic, or complete roadmap |
| Commit | Stop in `until-commit` and `end-to-end`; never auto-advance |

Commit remains optional as an integration action, but direct advance cannot cross dirty reviewed work. Commit the reviewed set or explicitly abandon it before activating the next epic.

## Work Ownership

- Plan creates initial roadmap or ledger state.
- Implement writes code but never declares epic completion.
- Verify owns verification readiness.
- Review owns review result and epic completion.
- Fixup returns changed code to verification.
- Advance owns creation of the next epic ledger.
- Commit, PR, and archive own only their named lifecycle actions.

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

Clearly unrelated dirty files may coexist with active work only when active-scope ownership is provable. Review and commit must exclude and preserve them.

## Retired Invariants

None.
