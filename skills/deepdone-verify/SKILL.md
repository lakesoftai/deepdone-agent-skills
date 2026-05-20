---
name: deepdone-verify
slug: deepdone-verify
description: Verify changes with smallest relevant checks first, widen only when shared impact requires it, and log exact commands and outcomes. Use before claiming a milestone or task is done.
---

# DeepDone Verify

## Purpose

Make verification deterministic and scoped.

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

## Mandatory Notes

Record exact command and result.
If something could not run, state exact blocker.
Do not claim pass based on intent.

## Ledger Writeback

Append lines under `## Verification Log` such as:

```md
- command: `just test api-auth`
  result: pass
  notes: focused auth test passed
- command: `uv run pytest tests/test_auth.py`
  result: fail
  notes: login fixture broken after schema change
- command: `just lint`
  result: blocked
  notes: no `justfile` in repo
```

`result:` is required. Use only `pass`, `fail`, or `blocked`.

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
3. Run it.
4. Decide whether broader checks are needed.
5. Run broader checks only where justified.
6. Log every command and outcome with `result:`.
7. State residual risk if coverage still incomplete.

## Output

Return:

- checks run
- pass, fail, or blocked status
- residual risk
