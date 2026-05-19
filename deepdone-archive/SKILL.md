---
name: DeepDone Archive
slug: deepdone-archive
description: Archive a completed DeepDone epic after explicit user request or clear supervisor-provided merge/release reference, update roadmap pointers, and preserve post-merge verification truth.
---

# DeepDone Archive

## Purpose

Close the post-commit loop after work has merged or otherwise been released.

This skill archives completed epic state.
It is not roadmap advancement, PR creation, merge, or deploy.

Archive only when explicitly requested or when supervisor context includes a clear merge or release reference.

## Inputs

Prefer explicit:

- roadmap path
- epic ledger path
- merge commit, PR/MR URL, release tag, or equivalent reference
- post-merge verification command or outcome if already known

If merge or release reference is missing, stop and ask for it.

## Preconditions

Before editing:

- no `.deepdone/STOP` exists
- target epic ledger exists
- target epic is complete
- merge or release reference is clear
- archive destination does not already exist
- roadmap, if present, points to the target epic or completed queue entry

Do not archive active unfinished work.
Do not delete ledgers.
Do not advance to the next epic here unless user explicitly asks.

## Archive Rules

Move completed ledger from:

```text
notes/epics/<file>.md
```

to:

```text
notes/archive/epics/<file>.md
```

Update roadmap references:

- completed epic queue item `ledger:` points to archived path
- if `Active Epic.ledger` was the archived ledger, set:
  - `name: none`
  - `ledger: none`
  - `state: none`

Append archive note to the archived ledger under `## Status` or existing final-status text:

```md
archived
- archived: YYYY-MM-DD
- merge/ref: <merge commit, PR/MR URL, release tag, or equivalent>
- post-merge verification: pass|fail|blocked|not-run
```

If post-merge verification is relevant and discoverable, run or request it before archive completion.
If it cannot run, record exact blocker and residual risk.

## Workflow

1. Locate roadmap and target epic ledger.
2. Confirm explicit archive request or supervisor merge/release context.
3. Confirm epic is complete and safe to archive.
4. Determine archive path.
5. Move ledger to `notes/archive/epics/`.
6. Update roadmap ledger pointers and active epic fields.
7. Record archive note and post-merge verification truth.
8. Report archived path, roadmap updates, checks, and next action.

## Output

Return:

- archived ledger path
- roadmap path and updates
- merge or release reference
- post-merge verification result
- residual risk
- next action
