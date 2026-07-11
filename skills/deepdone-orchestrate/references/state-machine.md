# DeepDone Workflow Contract

Read this reference before classifying or routing DeepDone work. This file is the authoritative lifecycle contract.

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
  notes: no blocking findings
```

Allowed results: `pending`, `pass`, `fail`, `blocked`.

Latest entry wins. Missing `## Review` means `pending`. Add the section during review or sync when needed; do not require bulk migration.

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
4. `needs_advance_roadmap`: user invoked advance, or a later supervisor run finds a reviewed complete epic that must activate queued work or finalize roadmap completion, and current mode does not require commit first.
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

Commit is optional before advance. Direct advance may proceed with expected reviewed epic changes still dirty, but must stop for unrelated, unreviewed, or ambiguous changes.

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
- roadmap points to one epic while current changes clearly belong to another, except the immediately preceding reviewed epic plus deterministic advance-state files after an explicit advance
- dirty files are unrelated or ownership is unknown
- reconciling would require product, architecture, security, migration, or data-risk judgment
