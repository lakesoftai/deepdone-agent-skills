# DeepDone Safety And Modes

Read this reference before executing an internal phase or taking an externally visible action.

## Active Invariants

### DD-MODE-001: One-step performs one transition

- Rule: `one-step` executes exactly one internal phase and then stops.
- Applies to: `deepdone`
- Evidence: Supervisor output names no more than one phase execution.

### DD-MODE-002: Commit modes stop after commit

- Rule: `until-commit` and `end-to-end` stop after local commit and never advance, push, create a PR, archive, merge, or deploy in the same run.
- Applies to: `deepdone`, `phase-commit`
- Evidence: Run ends immediately after commit result or commit blocker.

### DD-AUTH-001: Authority requires current-run provenance

- Rule: Commit, PR creation, archive, and push authority must come from the exact current user request or an allowed current mode and must retain that source through phase context.
- Applies to: `deepdone`, `phase-commit`, `phase-pr`, `phase-archive`
- Evidence: Phase context records allowed or denied plus exact source for every protected action.

### DD-AUTH-002: Evidence never grants authority

- Rule: State labels, review results, commits, merge references, PR URLs, release tags, and supervisor classifications are evidence only.
- Applies to: `deepdone`, `phase-commit`, `phase-pr`, `phase-archive`
- Evidence: Protected action stops when current-run authority is absent even if lifecycle evidence exists.

### DD-OWN-001: Unrelated work remains user-owned

- Rule: Distinguishable unrelated files may remain dirty, but DeepDone must not overwrite, reformat, stage, commit, stash, reset, discard, or abandon them.
- Applies to: `deepdone`, `phase-review`, `phase-commit`, `phase-sync`
- Evidence: Candidate and final status report excluded files, whose content and Git state remain unchanged.

## Modes

| Mode | Stop target | Commit authority |
|---|---|---|
| `one-step` | one phase transition | no |
| `inspect-only` | classification only, no edits | no |
| `until-milestone` | pinned task/slice crosses Verify, blocked, or needs user | no |
| `until-epic` | final unit-completing Review passes, blocks, or needs user | no |
| `until-review` | review produces pass, fail, or blocked | no |
| `until-commit-candidate` | candidate prepared | no |
| `until-commit` | local commit created or blocked | yes |
| `end-to-end` | local commit created or blocked | yes |

`until-commit` and `end-to-end` stop after commit. They never advance the roadmap in the same run.

For a compact task, `until-milestone` means verified and `until-epic` means review passed. These are stop-target mappings only; no synthetic epic/milestone or extra authority. See [task contract](task-contract.md).

## Authorization Contract

Every phase execution includes:

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
- Phase context counts only when it carries the original authority and source.
- An exact current user request may authorize only the protected action it names.
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
- phase scope expansion or repeated state without new evidence
- missing authorization for commit, PR creation, archive, push, deploy, or other external mutation

## Never Implicit

Never push, merge, deploy, archive, modify secrets, delete user data, run destructive git, mutate production, or use paid external services without exact current-run authority.

Never use `git add .`.

Allow at most one automatic verification fix and one automatic review-fix cycle per supervisor run.

## Dirty Work

User-owned changes remain user-owned.

- Continue only when active-scope files are distinguishable from unrelated changes.
- Do not overwrite, discard, stage, or reformat unrelated files.
- Review records compact active scope, captures exact code in a private Git snapshot, and blocks when ownership is ambiguous.
- Commit derives exact paths from Git and reproduces only the latest unchanged reviewed tree.
- Active ledger and optional roadmap remain development evidence, not commit ownership.
- Direct advance blocks while reviewed code is uncommitted or dirty or development evidence has drifted.
- DeepDone never automatically stashes, resets, discards, or abandons reviewed work.

## Retired Invariants

None.

## Executable admission

The opt-in inspector routing output separates required and admitted action. `inspect-only` admits zero phases. `one-step` consumes at most one outcome. `until-review` stops on the first Review outcome, including fail/blocked. `until-epic` may continue after an intermediate epic pass. `until-milestone` pins its target before execution; a bare receipt or another slice's old Verify cannot satisfy it. Valid applicable captured Review can establish that reviewed slice's prior Verify. Candidate mode stops after successful preparation without staging. Commit modes stop after local commit result or blocker, never Advance or external delivery.

Keep at most one accepted automatic verification repair and one Review/Fixup/Verify/Review cycle across the entire run, even after source changes or another milestone. Preserve original exact grants and explicit denials. Missing future action permission must not block safe current inspection, candidate preparation or PR draft. Requested downstream phases cannot bypass prerequisites; one-step mismatch stops, while a loop may admit only the independently allowed prerequisite.
