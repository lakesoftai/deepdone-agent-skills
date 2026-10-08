# Fixup Phase

For a selected compact task, apply the [task contract](task-contract.md) and carry its explicit `--task` selector through every helper. Epic-only roadmap/milestone rules below do not apply to tasks.

## Conforms To

- `DD-STATE-002`

## Purpose

Repair one accepted local problem without expanding scope. The supervisor supplies the precise action:

- `fixup`: an applicable accepted local Review finding, followed by feedback, Verify and Review.
- `verification-repair`: an accepted obvious local cause of a failed required check, followed by feedback and Verify. A failed diagnostic reproducer alone does not authorize this action.

Keep the two existing run-wide repair allowances separate. A changed repair owes Verify even while the previous failed readiness receipt remains in history. A subsequent unresolved required failure stops; source changes never reset the allowance.

This internal phase is allowed to fix findings only when they are:

- accepted,
- local,
- low risk,
- clearly correct,
- within the active milestone or active epic,
- verifiable with a targeted check.

When findings require prioritization, architecture judgment, product behavior changes, security judgment, or broad refactoring, stop and ask the user.

## Inputs

For `fixup`, prefer explicit review findings from the user or a review output file. For `verification-repair`, inspect the actual failed required receipt, check definition and accepted local cause. Carry the selected identity/slice and source applicability through either action.

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

The stop list applies when the relevant judgment or authority is unresolved. Restoring an explicit, unambiguous authorized requirement does not create a new policy decision. Reviewer advice cannot supply missing authority.

## Scope Rules

- Fix only the accepted finding or failed-check cause for the admitted action.
- Do not start the next milestone.
- Do not opportunistically refactor.
- Do not rewrite unrelated code.
- Do not update roadmap except when epic status is affected.
- Update ledger only with review-fix truth.

## Workflow

1. Locate active work unit.
2. Read the admitted action’s evidence and related diff. Confirm a behavioral reproducer fails for the intended symptom, not a setup failure.
3. Classify findings into auto-fix, needs user, or reject as non-actionable.
4. If any high-risk finding exists, stop and ask before editing.
5. Fix only the accepted local cause. Reject unsupported advice with a concrete reason and preserve correct code.
6. Run the smallest verification command that proves the fix.
7. Broaden verification only if shared or risky code was touched.
8. Update active epic ledger:
   - record fixed findings in `## Decisions` or `## Open Loops`, whichever already fits the ledger truth,
   - append exact checks under `## Verification Log` with `command:`, `result: pass|fail|blocked`, and `notes:`,
   - append a `## Review` entry with `reviewed-at: not-run`, `result: pending`, and notes that fixup changed code,
   - update `Next Action` to run the Verify phase through `$deepdone`.
9. Record the changed outcome with its precise action, retain historical evidence and consumed budgets, and return changed code through Verify before Review or another repair.
10. Return result block.

Checks run during fixup prove the local repair only. They do not skip the Verify transition. Use purpose `feedback` for captured fixup checks. Verify requires an actual `readiness` execution; feedback cannot be promoted. See [verification contract](verification-contract.md).

## Ledger Write Policy

Do not create new sections.

Use existing sections:

- `## Decisions`: accepted review-fix choice or cleanly rejected non-issue.
- `## Verification Log`: exact commands and structured `result: pass|fail|blocked` markers.
- `## Open Loops`: findings that remain unresolved or require user decision.
- `## Next Action`: one exact next step.
- `## Review`: append pending state after code changes; latest entry wins.
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
