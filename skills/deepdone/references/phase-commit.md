# Commit Phase

## Purpose

Prepare or create a focused git commit for completed DeepDone work.

## Conforms To

- `DD-STATE-001`, `DD-MODE-002`
- `DD-AUTH-001`, `DD-AUTH-002`
- `DD-OWN-001`, `DD-REVIEW-001`, `DD-EVIDENCE-001`
- `DD-COMMIT-001`, `DD-COMMIT-002`

This internal phase is a safety gate, not a formatting helper.

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

Do not treat `ready_to_commit`, another state label, a clean review, or phase context without authority source as authorization.

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
- latest passing Review has `review-id`, `base-head`, `manifest`, compact `scope`, and recognized `evidence`,
- schema-v2 reviewed change-set manifest validates against private review ref and current contents,
- current worktree projection over Git-derived reviewed paths equals reviewed tree,
- active ledger and optional roadmap hashes remain unchanged,
- no staged path exists outside Git-derived reviewed set,
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
python3 <skill-dir>/scripts/commit_progress.py --candidate
```

For an actual commit, use the harness when commit is authorized:

```bash
python3 <skill-dir>/scripts/commit_progress.py --commit --yes --authorized-by <exact-user-request|mode> --reviewed-change-set .deepdone/reviews/<review-id>.json
```

Resolve `<skill-dir>` as the loaded `deepdone` directory containing this reference. Do not expect the helper under the target repository's root `scripts/` directory.

Do not run `git add .`.

When the supervisor provides a ledger path, pass `--ledger <path>` to the harness. This is required when multiple completed single-epic ledgers exist.

The harness asks Git for exact paths between `base-head` and private `review_ref`. It never reads a bulk path list from Markdown or JSON.

Before commit, harness:

- rebuilds reviewed tree from current files through a temporary index
- verifies ledger and optional roadmap filesystem hashes
- rejects schema-v1 manifests for dirty work
- copies exact reviewed tree entries into real index
- checks real index tree equals reviewed tree
- commits real index
- checks resulting commit tree equals reviewed tree

Candidate output stays bounded: count, compact scope, Git ref and tree, and small status samples only. It reports and preserves unrelated unstaged or untracked work. Any unrelated staged path blocks actual commit. It must not create repo-local candidate files by default. Candidate output should go to stdout unless the user explicitly asks for a file.

Successful commit retains schema-v2 manifest and private review ref. Advance owns cleanup after its durable state transition.

If the bundled harness is unavailable, stop. Do not reproduce manifest validation or exact-set staging manually.

If the environment refuses writes to `.git/index`, `.git/HEAD`, or refs, report that as an environment permission blocker. Do not fall back to writing git internals manually.

## Workflow

1. Inspect current git and DeepDone state.
2. Confirm commit eligibility.
3. If not eligible, stop and explain exact missing gate.
4. Prepare a candidate with:
   - summary,
   - reviewed Git path count, compact scope, and bounded status sample,
   - verification evidence,
   - review evidence,
   - residual risk,
   - commit message.
5. If user asked only for candidate, stop.
6. If commit is authorized, require explicit manifest path, validate it, reproduce exact reviewed index tree, and commit.
7. Verify resulting commit tree and report commit hash if created.
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
