# DeepDone Safety And Modes

Read this reference before invoking a child skill or taking an externally visible action.

## Active Invariants

### DD-MODE-001: One-step performs one transition

- Rule: `one-step` invokes exactly one child skill and then stops.
- Applies to: `deepdone-orchestrate`
- Evidence: Supervisor output names no more than one child invocation.

### DD-MODE-002: Commit modes stop after commit

- Rule: `until-commit` and `end-to-end` stop after local commit and never advance, push, create a PR, archive, merge, or deploy in the same run.
- Applies to: `deepdone-orchestrate`, `deepdone-commit`
- Evidence: Run ends immediately after commit result or commit blocker.

### DD-AUTH-001: Authority requires current-run provenance

- Rule: Commit, PR creation, archive, and push authority must come from the exact current user request or an allowed current mode and must retain that source through child prompts.
- Applies to: `deepdone-orchestrate`, `deepdone-commit`, `deepdone-pr`, `deepdone-archive`
- Evidence: Child context records allowed or denied plus exact source for every protected action.

### DD-AUTH-002: Evidence never grants authority

- Rule: State labels, review results, commits, merge references, PR URLs, release tags, and supervisor classifications are evidence only.
- Applies to: `deepdone-orchestrate`, `deepdone-commit`, `deepdone-pr`, `deepdone-archive`
- Evidence: Protected action stops when current-run authority is absent even if lifecycle evidence exists.

### DD-OWN-001: Unrelated work remains user-owned

- Rule: Distinguishable unrelated files may remain dirty, but DeepDone must not overwrite, reformat, stage, commit, stash, reset, discard, or abandon them.
- Applies to: `deepdone-orchestrate`, `deepdone-review`, `deepdone-commit`, `deepdone-sync`
- Evidence: Candidate and final status report excluded files, whose content and Git state remain unchanged.

## Modes

| Mode | Stop target | Commit authority |
|---|---|---|
| `one-step` | one child transition | no |
| `inspect-only` | classification only, no edits | no |
| `until-milestone` | active milestone verified, blocked, or needs user | no |
| `until-epic` | epic review passes, blocks, or needs user | no |
| `until-review` | review produces pass, fail, or blocked | no |
| `until-commit-candidate` | candidate prepared | no |
| `until-commit` | local commit created or blocked | yes |
| `end-to-end` | local commit created or blocked | yes |

`until-commit` and `end-to-end` stop after commit. They never advance the roadmap in the same run.

## Authorization Contract

Every child invocation includes:

```text
Authorizations:
- commit: allowed|denied; source: exact user request|mode|none
- pr-create: allowed|denied; source: exact user request|none
- archive: allowed|denied; source: exact user request|none
- push: allowed|denied; source: exact user request|none
```

Rules:

- Preserve exact current-run authority; do not infer it from earlier runs.
- `until-commit` and `end-to-end` authorize commit only.
- A state label such as `ready_to_commit` is evidence, not authority.
- A merge commit, release tag, or PR URL is evidence, not archive authority.
- Supervisor context counts only when it carries the original authority and source.
- Direct skill invocation may use the current user request as authority for that named action.
- Denial or ambiguity wins.

## Hard Stops

Stop immediately for:

- `.deepdone/STOP`
- ambiguous active roadmap or ledger
- blocking roadmap-ledger disagreement defined by the workflow contract
- unexpected or unexplained dirty files
- unclear next milestone or missing acceptance criteria
- non-trivial verification that cannot run
- review finding needing product, architecture, security, auth, migration, data-risk, or prioritization judgment
- child scope expansion or repeated state without new evidence
- missing authorization for commit, PR creation, archive, push, deploy, or other external mutation

## Never Implicit

Never push, merge, deploy, archive, modify secrets, delete user data, run destructive git, mutate production, or use paid external services without exact current-run authority.

Never use `git add .`.

Allow at most one automatic verification fix and one automatic review-fix cycle per supervisor run.

## Dirty Work

User-owned changes remain user-owned.

- Continue only when active-scope files are distinguishable from unrelated changes.
- Do not overwrite, discard, stage, or reformat unrelated files.
- Review records exact active-scope paths and blocks when ownership is ambiguous.
- Commit stages only the latest unchanged reviewed path set.
- Direct advance blocks while any reviewed path remains dirty.
- DeepDone never automatically stashes, resets, discards, or abandons reviewed work.

## Retired Invariants

None.
