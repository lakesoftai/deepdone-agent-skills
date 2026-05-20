---
name: deepdone-fixup
slug: deepdone-fixup
description: Triage and fix accepted local code review findings from a DeepDone workflow, verify the fix, update the epic ledger, and stop when findings require product or architecture judgment.
---

# DeepDone Fixup

## Purpose

Fix review findings without turning review into a new unbounded implementation phase.

Use this skill after `$deepdone-review` or an agent UI review has produced findings.

This skill is allowed to fix findings only when they are:

- accepted,
- local,
- low risk,
- clearly correct,
- within the active milestone or active epic,
- verifiable with a targeted check.

When findings require prioritization, architecture judgment, product behavior changes, security judgment, or broad refactoring, stop and ask the user.

## Inputs

Prefer explicit review findings from the user or a review output file.

If no findings are provided, inspect likely sources:

1. latest agent UI review comments if visible in the thread,
2. active epic ledger `Open Loops`,
3. recent review notes in `## Decisions` or `## Verification Log`,
4. git diff and recent conversation context.

If no concrete findings can be found, stop. Do not invent findings.

## What To Read

Read:

- active roadmap if present,
- active epic ledger,
- latest review findings,
- `git status --short`,
- `git diff`,
- files referenced by findings,
- relevant tests or verification commands,
- AGENTS instructions.

## Finding Triage

Classify each finding:

### Auto-fix allowed

Auto-fix is allowed for:

- local correctness bug,
- missing null or error handling,
- obvious off-by-one or condition bug,
- typo that breaks behavior,
- local test expectation update that follows intended behavior,
- small missing test for the changed behavior,
- local type/lint failure caused by current diff.

### Stop and ask user

Stop for:

- product behavior change,
- architecture or API design change,
- security or permission issue,
- auth/session issue,
- data deletion or migration risk,
- schema change,
- broad refactor,
- performance tradeoff with user-visible cost,
- multiple valid approaches,
- finding that conflicts with ledger constraints,
- finding outside active milestone or epic.

## Scope Rules

- Fix only review findings.
- Do not start the next milestone.
- Do not opportunistically refactor.
- Do not rewrite unrelated code.
- Do not update roadmap except when epic status is affected.
- Update ledger only with review-fix truth.

## Workflow

1. Locate active work unit.
2. Read review findings and related diff.
3. Classify findings into auto-fix, needs user, or reject as non-actionable.
4. If any high-risk finding exists, stop and ask before editing.
5. Fix only accepted local findings.
6. Run the smallest verification command that proves the fix.
7. Broaden verification only if shared or risky code was touched.
8. Update active epic ledger:
   - record fixed findings in `## Decisions` or `## Open Loops`, whichever already fits the ledger truth,
   - append exact checks under `## Verification Log` with `command:`, `result: pass|fail|blocked`, and `notes:`,
   - update `Next Action`.
9. If review should be rerun, set `Next Action` to run `$deepdone-review`.
10. Return result block.

## Ledger Write Policy

Do not create new sections.

Use existing sections:

- `## Decisions`: accepted review-fix choice or cleanly rejected non-issue.
- `## Verification Log`: exact commands and structured `result: pass|fail|blocked` markers.
- `## Open Loops`: findings that remain unresolved or require user decision.
- `## Next Action`: one exact next step.
- `## Status`: update only if the epic is blocked by findings.

## Verification Policy

Run at least one targeted check unless impossible.

If checks cannot run, record the blocker and residual risk.

Do not claim the fix is complete based on inspection only unless the finding was documentation-only or non-executable.

## Output

Return:

- active ledger path,
- findings fixed,
- findings deferred to user,
- files touched,
- checks run,
- next action,
- residual risk.
