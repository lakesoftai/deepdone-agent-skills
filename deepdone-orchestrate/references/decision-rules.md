# DeepDone Decision Rules

## Use Epic Intake

Use when requirements exist and no suitable durable DeepDone state exists.

## Use Resume Epic

Use when state exists but may be stale or inconsistent.

Signals:

- roadmap and ledger disagree
- git has unlogged changes
- latest verification predates code changes
- active milestone cannot be identified
- `Next Action` looks obsolete

## Use Advance Roadmap

Use when the current active epic is complete or the roadmap has no active epic but queued work remains.

## Use Tech Decision

Use before implementation when a meaningful technical choice is unresolved.

Examples:

- framework/library option
- storage or schema option
- auth or permission model
- deployment or migration approach
- external API integration strategy

## Use Implement Next

Use when exactly one milestone is next and the acceptance check is clear.

## Use Does It Work

Use when code changed and verification is missing, stale, or insufficient.

## Use Code Review

Use after implementation and verification, before commit readiness.

## Use Fix Review Findings

Use only for accepted, local, low-risk findings.

## Use Commit Progress

Use for commit candidate preparation when commit is not authorized. Use for actual commit when mode is `until-commit` or `end-to-end`, or the user explicitly asks to commit.

## Stop

Stop if a human would need to choose scope, product behavior, risk tolerance, or approval not already authorized by selected mode.
