# Verify Phase

For a selected compact task, apply the [task contract](task-contract.md) and carry its explicit `--task` selector through every helper. Epic-only roadmap/milestone rules below do not apply to tasks.

## Conforms To

- `DD-STATE-001`, `DD-STATE-002`

## Purpose

Keep verification deterministic and scoped.

## Verification Order

Start narrow. Widen only when impact demands it.

Typical order:

1. focused unit or smoke check nearest change
2. package or app lint
3. package or app typecheck
4. affected test suite
5. broader integration or full gate if shared code changed

If repo exposes shared wrappers, prefer `just <target>`.
If not, use repo's real package-level commands.

## Command Discovery

Before guessing commands, inspect repo affordances in this order:

1. `justfile` or `.justfile`: prefer named project wrappers.
2. `Makefile`: use focused targets like `test`, `lint`, `check`, or package-specific targets.
3. `package.json`: read `scripts`; prefer focused package scripts before broad `test`.
4. `pyproject.toml`: inspect tool config and project layout; prefer `uv run`, `pytest`, `ruff`, `mypy`, or repo wrappers already documented.
5. `Cargo.toml`: prefer `cargo test`, `cargo check`, or package-specific variants.
6. `go.mod`: prefer `go test ./...` only when package-level test is not obvious.
7. Existing CI config or README commands if no local wrapper is found.

Record discovery when it affects command choice:

```md
- command: discovery
  result: pass
  notes: found `justfile`; using `just test-auth` before broader checks
```

If discovery finds no runnable command, log a blocked entry with exact reason.

## Captured Readiness

Use the [verification execution contract](verification-contract.md). Declare the
current required/advisory inventory, acceptance conditions, exact commands and
complete input scope. Execute each required check through `scripts/verification.py`
with purpose `readiness`. Diagnostic and implementation feedback do not substitute
for an actual readiness execution. Reuse only an already eligible same-definition
readiness receipt whose current inputs still match.

The helper records a pending attempt before launch and captures raw outcomes,
input fingerprints, context, and bounded binary output. Run its `check` action to
validate the complete chain. Missing contract/checks, invalid references, pending
attempts, failure, or stale inputs block. Inspect specific blockers and preserve
history. Review must still judge whether the inventory covers acceptance.

Keep readable exact-command summaries in `## Verification Log`, using
`result: pass|fail|blocked` for display. They are not readiness authority. For
legacy ledgers, explicitly initialize the new contract with a migration reason,
preserve old text, execute real checks, and obtain a new review. Never convert an
old passing string into a receipt. See the contract for strict JSON shapes,
unsupported context, generated exclusions, concurrency recovery, and limitations.

## Interpret results before claiming success

Confirm that the command exercised the intended behavior. Distinguish an expected diagnostic symptom from a setup failure, and a meaningful successful check from an empty selection. Preserve both results honestly. Recheck the reproducer and affected original behavior after correction; a final readiness execution or eligible current readiness receipt remains required. Test quantity is not a substitute for acceptance coverage.

A failed required check may permit one accepted, obvious local `verification-repair` through Fixup. After changed repair, cross Verify again before reviewing or requesting another repair; the old failed receipt remains historical evidence. Keep its repair allowance consumed across source and slice changes. An unresolved subsequent failure stops for its exact cause.

## Risk Triggers

Broaden verification when change touches:

- shared libs
- auth or permissions
- schema or migrations
- external APIs
- config or deployment-sensitive paths
- user-visible flows

## Workflow

1. Discover command wrappers and package-level checks.
2. Identify smallest convincing check.
3. Declare the complete current check inventory and run required checks through the wrapper.
4. Decide whether broader checks are needed.
5. Run broader checks only where justified.
6. Validate captured receipts and freshness; retain readable command summaries.
7. If required checks pass, keep epic `Status: active` and set `Next Action` to run the Review phase through `$deepdone`.
8. If a required check fails or blocks, record the issue in `Open Loops`, keep review pending, and set one exact fix or unblock action.
9. State residual risk if coverage still incomplete.

Do not mark an epic complete or roadmap state `complete-pending-advance`. Review owns completion.

## Output

Return:

- checks run
- pass, fail, or blocked status
- residual risk
- exact next action
