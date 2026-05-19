# DeepDone Skills

DeepDone is a small skill package for agent-driven software work. It keeps long work recoverable by using one roadmap, one active epic ledger, and narrow workflow skills.

Works best with Codex.

## Start Here

For normal use, invoke the supervisor:

```text
Use $deepdone-orchestrate.
Requirements: <some-requirements>
Mode: end-to-end.
```

or:

```text
Use $deepdone-orchestrate to implement these requirements end to end: @some-requirements.md
```


Useful modes:

- `one-step`: do one transition, then stop
- `inspect-only`: classify state without edits
- `until-milestone`: finish current milestone
- `until-epic`: finish current epic without commit
- `until-review`: run through review
- `until-commit-candidate`: prepare commit candidate only
- `until-commit`: create local commit after gates pass
- `end-to-end`: full intake to commit, capped at 60 child calls

Post-commit work uses direct skills:

- `deepdone-pr`: draft PR/MR text, optionally create or inspect CI only when explicitly requested
- `deepdone-archive`: archive completed epic state after merge or release reference

## Workflow

Core path:

```text
requirements -> plan -> sync -> advance -> decide -> implement -> verify -> review -> fixup -> commit -> pr -> archive
```

Loop path: after review, use `fixup`, then verify and review again as needed.

The supervisor routes between skills. Direct child skill invocation is useful only when you already know the exact workflow stage.

`pr` and `archive` are conservative post-commit steps:

- PR/MR drafting is default and platform-neutral.
- PR/MR creation needs explicit approval, clear remote, target branch, branch publish state, and available repo tooling.
- Archive needs explicit request or supervisor context with merge commit, PR/MR URL, release tag, or equivalent reference.
- Push, merge, deploy, and archive are never implicit.

## Skills

- `deepdone-orchestrate`: supervises routing, budgets, and safety gates
- `deepdone-plan`: classifies scope and creates roadmap or epic ledger
- `deepdone-sync`: reconciles ledger, code, and git state after interruption
- `deepdone-advance`: moves a roadmap from completed active epic to next queued epic
- `deepdone-decide`: records one technical decision with evidence
- `deepdone-implement`: executes exactly one milestone
- `deepdone-verify`: runs smallest convincing checks and logs structured results
- `deepdone-review`: reviews local diff for bugs, regressions, security, and test gaps
- `deepdone-fixup`: fixes accepted local review findings
- `deepdone-commit`: prepares or creates a gated local commit
- `deepdone-pr`: prepares platform-neutral PR/MR drafts and inspects CI for existing PRs
- `deepdone-archive`: archives completed epic state after explicit merge or release reference

## Safety

- `.deepdone/STOP` stops all DeepDone work
- no push, merge, deploy, archive, destructive git, production mutation, or data deletion without explicit approval
- commit only in `until-commit`, `end-to-end`, or explicit commit request
- PR/MR creation only after explicit request and clear repo tooling
- archive only after explicit request or clear merge/release reference
- never use `git add .`
- commit harness rejects likely secrets and local-only files

## License

See [LICENSE](LICENSE).

## Examples

See:

- [examples/roadmap.md](examples/roadmap.md)
- [examples/single-epic-ledger.md](examples/single-epic-ledger.md)
- [examples/multi-epic-active-ledger.md](examples/multi-epic-active-ledger.md)
- [examples/commit-candidate.md](examples/commit-candidate.md)
- [examples/pr-body.md](examples/pr-body.md)
- [examples/archived-epic-ledger.md](examples/archived-epic-ledger.md)
- [examples/post-merge-roadmap.md](examples/post-merge-roadmap.md)
- [examples/run-audit.jsonl](examples/run-audit.jsonl)

## Self-Test

Run:

```bash
python3 scripts/doctor.py
```

Doctor checks skill metadata, OpenAI manifests, helper scripts, examples, and unit tests.
