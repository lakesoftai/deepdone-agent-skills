# DeepDone Skills

DeepDone is a two-skill package for agent-driven software work. It supports single-step or bounded end-to-end implementation from planning through a reviewed local commit. PR and archive actions remain separate and explicit.

It keeps long work recoverable through one roadmap, one active epic ledger, and narrow internal workflow phases.

## Installation

Install both public DeepDone skills with the skills CLI:

```bash
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone-orchestrate --skill deepdone-advance
```

Install globally:

```bash
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone-orchestrate --skill deepdone-advance -g
```

Use `-a` to install for a specific agent :

```bash
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone-orchestrate --skill deepdone-advance -a codex
```

### Upgrade from the twelve-skill package

The ten former child skills are no longer public entry points. If an existing selector still shows them, remove those stale installs before reinstalling the two public skills:

```bash
npx skills remove -y deepdone-plan deepdone-sync deepdone-decide deepdone-implement deepdone-verify deepdone-review deepdone-fixup deepdone-commit deepdone-pr deepdone-archive
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone-orchestrate --skill deepdone-advance
```

Add `-g` to both commands for a global install. Add `-a codex` to target only Codex. Use the CLI removal command instead of deleting directories by hand so install links and unused canonical copies are cleaned together. Global removal also cleans the selected skills from the global skill lock.

After cleanup, direct calls such as `$deepdone-review` do not resolve. Use `$deepdone-orchestrate` with `Requested phase: review`. The same pattern applies to every removed child name.

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
- `end-to-end`: full intake to local commit, bounded by safety gates

Post-commit work remains routed through the supervisor:

- `Use $deepdone-orchestrate to prepare a PR/MR draft for the current DeepDone work.`
- `Use $deepdone-orchestrate to archive <ledger path> after merge/ref <reference>.`

## Workflow

Core path:

```text
requirements -> plan -> sync -> advance -> decide -> implement -> verify -> review -> fixup -> commit -> pr -> archive
```

Loop path: after review, use `fixup`, then verify and review again as needed.

The supervisor classifies repository state, then loads exactly one matching internal phase. For targeted control, request the phase through the supervisor, such as `Use $deepdone-orchestrate. Requested phase: review.` The request never bypasses state or authorization gates.

`pr` and `archive` are conservative post-commit steps:

- PR/MR drafting is default and platform-neutral.
- PR/MR creation needs explicit approval, clear remote, target branch, branch publish state, and available repo tooling.
- Archive needs explicit current-run user authority plus a merge commit, PR/MR URL, release tag, or equivalent reference.
- Push, merge, deploy, and archive are never implicit.

## Public Skills

- `deepdone-orchestrate`: supervises the complete workflow, internal phase routing, and safety gates
- `deepdone-advance`: moves a roadmap from completed active epic to next queued epic

## Internal Phases

Plan, sync, decide, implement, verify, review, fixup, commit, PR, and archive remain bundled under `deepdone-orchestrate`. They are reference modules, not discoverable `SKILL.md` entry points. The supervisor loads only the phase required by classified repository state.

## Safety

- `.deepdone/STOP` stops all DeepDone work
- no push, merge, deploy, archive, destructive git, production mutation, or data deletion without explicit approval
- commit only in `until-commit`, `end-to-end`, or explicit commit request
- PR/MR creation only after explicit request and clear repo tooling
- archive only after explicit current-run request and clear merge/release reference
- never use `git add .`
- commit harness rejects likely secrets and local-only files
- passing review records exact paths plus ignored deterministic evidence under `.deepdone/reviews/`
- commit harness accepts only unchanged reviewed paths and preserves unrelated unstaged work
- reviewed paths must be clean before roadmap advance

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

## Self-Test

Run:

```bash
python3 scripts/doctor.py
```

Doctor checks exactly two public skills, ten internal phases, skill metadata, OpenAI manifests, invariant conformance, reviewed change-set schema compatibility, helper scripts, examples, logging removal, and unit tests.

## Manual Cross-Agent Evaluation

List or preflight without agent work:

```bash
python3 evals/run_cross_agent.py --list
python3 evals/run_cross_agent.py --preflight
```

Run smoke manually with installed Codex and Claude Code credentials:

```bash
python3 evals/run_cross_agent.py --profile smoke --output-dir /tmp/deepdone-evals
```

Release evaluation requires explicit model names and runs every scenario three times in both harnesses:

```bash
python3 evals/run_cross_agent.py --profile release --codex-model <model> --claude-model <model> --output-dir /tmp/deepdone-evals-release
```

Live evaluation is never part of doctor or normal unit tests.
Every live run starts with a mandatory project-local skill-discovery probe and skips behavioral scenarios for that agent if discovery fails.
