# DeepDone

DeepDone is one public skill for agent-driven software work. It supports single-step or bounded end-to-end implementation from planning through a reviewed local commit. PR and archive actions remain separate and explicit.

It keeps long work recoverable through one roadmap, one active epic ledger, and narrow internal workflow phases.

## Installation

Install DeepDone with the skills CLI:

```bash
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone
```

Install globally:

```bash
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone -g
```

Use `-a` to install for a specific agent :

```bash
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone -a codex
```

### Upgrade from an older DeepDone package

Older releases exposed either twelve skills or two public skills. Remove all stale selector entries before installing `deepdone`:

```bash
npx skills remove -y deepdone-orchestrate deepdone-advance deepdone-plan deepdone-sync deepdone-decide deepdone-implement deepdone-verify deepdone-review deepdone-fixup deepdone-commit deepdone-pr deepdone-archive
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone
```

Add `-g` to both commands for a global install. Add `-a codex` to target only Codex. Use the CLI removal command instead of deleting directories by hand so install links and unused canonical copies are cleaned together. Global removal also cleans the selected skills from the global skill lock.

After cleanup, old calls such as `$deepdone-orchestrate`, `$deepdone-advance`, and `$deepdone-review` do not resolve. Use `$deepdone` with an optional request such as `Requested phase: review`. A requested phase never bypasses workflow or authorization gates.

## Start Here

For normal use, invoke DeepDone:

```text
Use $deepdone.
Requirements: <some-requirements>
Mode: end-to-end.
```

or:

```text
Use $deepdone to implement these requirements end to end: @some-requirements.md
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

Post-commit work remains routed through DeepDone:

- `Use $deepdone to prepare a PR/MR draft for the current DeepDone work.`
- `Use $deepdone to archive <ledger path> after merge/ref <reference>.`

## Workflow

Core path:

```text
requirements -> plan -> sync -> advance -> decide -> implement -> verify -> review -> fixup -> commit -> pr -> archive
```

Loop path: after review, use `fixup`, then verify and review again as needed.

DeepDone classifies repository state, then loads exactly one matching internal phase. For targeted control, request the phase through the same skill, such as `Use $deepdone. Requested phase: review.` The request never bypasses state or authorization gates.

`pr` and `archive` are conservative post-commit steps:

- PR/MR drafting is default and platform-neutral.
- PR/MR creation needs explicit approval, clear remote, target branch, branch publish state, and available repo tooling.
- Archive needs explicit current-run user authority plus a merge commit, PR/MR URL, release tag, or equivalent reference.
- Push, merge, deploy, and archive are never implicit.

## Public Skill

- `deepdone`: supervises the complete workflow, internal phase routing, and safety gates

## Internal Phases

Plan, sync, advance, decide, implement, verify, review, fixup, commit, PR, and archive are bundled under `deepdone`. They are reference modules, not discoverable `SKILL.md` entry points. DeepDone loads only the phase required by classified repository state.

## Safety

- `.deepdone/STOP` stops all DeepDone work
- no push, merge, deploy, archive, destructive git, production mutation, or data deletion without explicit approval
- commit only in `until-commit`, `end-to-end`, or explicit commit request
- PR/MR creation only after explicit request and clear repo tooling
- archive only after explicit current-run request and clear merge/release reference
- never use `git add .`
- commit harness rejects likely secrets and local-only files
- passing review stores exact code as private Git snapshot and keeps compact deterministic evidence under `.deepdone/reviews/`
- ignored epic ledger and optional roadmap are filesystem-hashed development evidence, never automatic commit candidates
- manifest stores Git object IDs and path count, not one JSON record per changed file
- commit harness reproduces only unchanged reviewed tree and preserves unrelated unstaged work
- reviewed snapshot must be committed and clean before roadmap advance

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

Doctor checks exactly one public skill, eleven internal phases, skill metadata, the OpenAI manifest, invariant conformance, reviewed change-set schema compatibility, helper scripts, examples, logging removal, and unit tests.

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
