---
name: DeepDone Advance
slug: deepdone-advance
description: Move a multi-epic initiative from the completed active epic to the next queued epic. Update the roadmap, create exactly one new active epic ledger, and keep future epics queued. Use only when the current active epic is complete or when a roadmap exists with no active epic yet. Trigger question: "Did I just finish the current epic?"
---

# DeepDone Advance

## Purpose

Advance a multi-epic initiative without creating planning sprawl.

This skill is the only default mechanism that should:

- rotate the active epic in a roadmap
- create the next epic ledger
- mark a roadmap complete when no queued epics remain

It must not start parallel active epics unless the user explicitly asks for parallel work.

## Preconditions

Before advancing, confirm one of these is true:

1. roadmap exists and `Active Epic.state` is `complete-pending-advance`, or
2. roadmap exists and there is no active epic yet, or
3. roadmap exists and current active epic ledger is clearly complete even if roadmap state is stale

If the active epic is not truly complete, stop and explain why advancing is premature.

## What To Read

Read the roadmap:

- `Summary`
- `Constraints`
- `Cross-Cutting Decisions`
- `Epic Queue`
- `Active Epic`
- `Status`

If an active epic ledger exists, read:

- `Summary`
- `Milestones`
- `Decisions`
- `Verification Log`
- `Open Loops`
- `Status`

If source material is referenced by the roadmap or still present in context, use it to sharpen the next epic, but do not regenerate the whole roadmap.

## Roadmap Rules

- exactly one active epic by default
- future epics remain queue-level only
- create exactly one new epic ledger per advance
- preserve completed epic entries and ledger paths
- do not reorder queued epics unless dependency or constraint evidence requires it
- if dependency or verification reality forces reordering, state the reason explicitly in roadmap notes or queue text

## Next Epic Selection Rules

Choose the next epic by these priorities:

1. first queued epic whose dependencies are satisfied
2. smallest execution lane that keeps architecture coherent
3. earliest epic with a clear verification story

Do not choose an epic that is still blocked on an unresolved decision from a prior epic unless that decision is explicitly listed and handled first.

## New Epic Ledger Rules

Create one new ledger at:

`notes/epics/YYYY-MM-DD-<slug>.md`

Use the standard epic headings:

```md
# <Epic title>

## Summary

## Constraints

## Milestones

## Decisions

## Verification Log

## Open Loops

## Next Action

## Status
```

Populate it with:

- narrow epic goal
- relevant inherited constraints from roadmap
- 3 to 7 verifiable milestones
- one exact next action
- `Status: active`

Carry forward only what the next epic actually needs:

- hard constraints
- relevant cross-cutting decisions
- dependency outcomes
- unresolved decisions that still matter
- interface contracts proved by prior epic

Do not copy old verification logs or stale open loops that no longer matter.

## Plan Mode Policy

Use your runtime's planning mode by default when available.
Advancing a roadmap requires confirming the next epic is still the right execution unit, dependencies are satisfied, and sequencing still fits repo reality.
If no planning mode exists, write a compact advancement plan and stop before edits.

## Workflow

1. Locate the roadmap.
2. Verify the current active epic is complete, or confirm there is no active epic yet.
3. Mark the completed epic entry `[x]` if needed.
4. Select the next queued epic whose dependencies are satisfied.
5. Create exactly one new epic ledger for that epic.
6. Update that epic queue entry from `[ ]` to `[-]`.
7. Write the new ledger path into the chosen queue item.
8. Update `Active Epic` to the new epic name, ledger path, and `state: active`.
9. If no queued epics remain, set:
   - `Active Epic` to `name: none`, `ledger: none`, `state: none`
   - roadmap `Status` to `complete`
10. Return the new active epic and exact next action.

## Guardrails

- do not create milestone plans for more than one future epic
- do not silently skip blocked dependencies
- do not keep roadmap `Status: active` if no queued or active epics remain
- do not reopen a completed epic unless user explicitly asks
- do not mutate unrelated epic ledgers

## Output

Return:

- exact roadmap path
- previous active epic and completion status
- new active epic, or roadmap-complete verdict
- exact new ledger path if created
- milestone list with acceptance checks for the new active epic
- exact next action
