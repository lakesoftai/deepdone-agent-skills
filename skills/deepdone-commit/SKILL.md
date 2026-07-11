---
name: deepdone-commit
slug: deepdone-commit
description: Prepare or create a safe focused git commit for completed DeepDone work after ledger, verification, and review gates pass. Use when the user asks for a commit candidate, asks to commit, or a supervisor mode authorizes commit.
---

# DeepDone Commit

## Purpose

Prepare or create a focused git commit for completed DeepDone work.

This is a safety gate, not a formatting helper.

Default behavior is commit candidate only when intent is unclear. Commit only when the current user request explicitly asks for commit, or supervisor context carries `commit: allowed` with source `mode` or `exact user request`.

Do not ask for permission to commit. Either commit after gates pass, or stop with exact blockers.

Never push.

## Inputs

The user may ask for:

- commit candidate only,
- actual commit,
- commit message draft,
- staging plan.

If unclear, prepare candidate only.

Treat these as commit authorization for the current run:

- direct user request to commit,
- mode `until-commit`,
- mode `end-to-end`,
- supervisor authorization block with `commit: allowed` and source `mode` or `exact user request`.

Do not treat `ready_to_commit`, another state label, a clean review, or a child prompt without authority source as authorization.

Treat these as commit denial:

- `do not commit`,
- `candidate only`,
- `commit candidate only`,
- `prepare only`.

## Preconditions

Before preparing a commit candidate, inspect:

- `git status --short --untracked-files=all`,
- `git diff --stat`,
- active roadmap if present,
- active epic ledger,
- latest `Verification Log`,
- latest `## Review` result, or legacy structured `review-result: pass|fail|blocked`,
- `Open Loops`,
- AGENTS instructions.

Before actual commit, all must be true:

- commit is authorized by current request or explicit supervisor authorization block,
- no `.deepdone/STOP` file exists,
- changed files are expected,
- active ledger is current,
- verification entries include `result: pass|fail|blocked`, and no failed or blocked check remains unaccepted,
- latest review result is `pass`,
- no unresolved Open Loop blocks this commit,
- commit message accurately describes the diff,
- no dangerous files are included.

Read the latest `## Review` entry when present. For legacy ledgers without that section, accept the latest structured `review-result: pass|fail|blocked` evidence. Missing review evidence blocks actual commit.

## Dangerous Files

Do not commit files that appear to contain secrets or local-only state unless the user explicitly approves and the repo policy allows it.

Examples:

- `.env`
- `.env.*`
- secret files
- private keys
- credentials
- tokens
- local database dumps
- generated build artifacts not normally committed
- `.deepdone/commit-candidate.md`
- local agent, editor, or orchestration scratch files

## Commit Harness

If available, use:

```bash
python3 scripts/commit_progress.py --candidate
```

For an actual commit, use the harness when commit is authorized:

```bash
python3 scripts/commit_progress.py --commit --yes --authorized-by <exact-user-request|mode>
```

Do not run `git add .`.

When the supervisor provides a ledger path, pass `--ledger <path>` to the harness. This is required when multiple completed single-epic ledgers exist.

After roadmap advance with reviewed predecessor changes still dirty, use the previous reviewed ledger path returned by `$deepdone-advance`. The current active ledger belongs the next epic and must not supply commit gates for predecessor work.

The harness stages exact files intentionally, including expected untracked files. It must not create repo-local candidate files by default. Candidate output should go to stdout unless the user explicitly asks for a file.

If the bundled harness is not available, use normal git commands directly:

1. inspect `git status --short --untracked-files=all`,
2. reject dangerous or local-only paths,
3. stage exact expected paths with `git add -- <path> ...`,
4. commit with `git commit -F <message-file>` or `git commit -m`,
5. report hash.

If the environment refuses writes to `.git/index`, `.git/HEAD`, or refs, report that as an environment permission blocker. Do not fall back to writing git internals manually.

## Workflow

1. Inspect current git and DeepDone state.
2. Confirm commit eligibility.
3. If not eligible, stop and explain exact missing gate.
4. Prepare a candidate with:
   - summary,
   - files to stage,
   - verification evidence,
   - review evidence,
   - residual risk,
   - commit message.
5. If user asked only for candidate, stop.
6. If commit is authorized, stage exact files and commit.
7. Report commit hash if created.
8. Never push.

## Commit Message Format

Use:

```text
<area>: <imperative summary>

DeepDone:
- Epic: <epic name or none>
- Milestone: <milestone or scope>
- Verification:
  - <command>: <result>
- Review:
  - <result>
```

Keep the subject under 72 characters when practical.

## Output

Return:

- candidate or commit result,
- files included,
- files excluded,
- checks considered,
- review gate status,
- commit message,
- next action.
