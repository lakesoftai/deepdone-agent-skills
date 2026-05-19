# DeepDone Skills

Agent-driven workflow management for software projects. Each skill does one thing. `deepdone-orchestrate` routes between them.

## Skills

| Skill | Role |
|---|---|
| `deepdone-orchestrate` | Supervisor: classifies state, routes to child skills, enforces mode budgets and safety gates |
| `deepdone-plan` | Classify scope (small task / single epic / multi-epic), create roadmaps and epic ledgers |
| `deepdone-sync` | Recover state after interruption, reconcile ledger vs code vs git |
| `deepdone-advance` | Move multi-epic initiative to next queued epic |
| `deepdone-decide` | Research and record one technical choice with evidence |
| `deepdone-implement` | Execute exactly one milestone |
| `deepdone-verify` | Verify changes: smallest check first, log exact commands |
| `deepdone-review` | Skeptical local diff review: correctness, regressions, security, overscope |
| `deepdone-fixup` | Fix accepted local review findings, stop on product/architecture judgment |
| `deepdone-commit` | Safe git commit with gate checks, dangerous-file detection |
| `deepdone-pr` | Prepare PR/MR draft, optional explicit creation, or inspect existing PR/MR CI |
| `deepdone-archive` | Archive completed epic state after explicit merge or release reference |

## Workflow

```text
requirements -> plan -> sync -> advance -> decide -> implement -> verify -> review -> fixup -> commit -> pr -> archive
                       ^                                      |
                       +------ resume loop after state drift --+
                                                         ^                 |
                                                         +-- review loop --+
```

The orchestrator (`deepdone-orchestrate`) drives this state machine. It inspects repo state, classifies the current position, and invokes the correct child skill.

`pr` and `archive` are post-commit lifecycle steps. They are not automatic side effects of commit:

- `deepdone-pr` drafts PR/MR text by default. Creation requires explicit approval plus clear remote, target branch, branch publish state, and repo-native tooling.
- `deepdone-archive` moves completed epic state only after explicit archive request or supervisor context with a clear merge/release reference.

## Quick Start

```
Use $deepdone-orchestrate.
Requirements: <your goal>
Mode: one-step.
```

For a full automation run through local commit:

```
Use $deepdone-orchestrate.
Requirements: <your goal>
Mode: end-to-end.
```

For post-commit handoff:

```
Use $deepdone-pr.
Prepare a PR/MR draft for the current DeepDone work.
```

For completed work archival:

```
Use $deepdone-archive.
Archive <ledger path> after merge/ref <PR URL, merge SHA, or release tag>.
```

## Key Concepts

- **Epic ledger**: `notes/epics/YYYY-MM-DD-<slug>.md`. Standard sections: Summary, Constraints, Milestones, Decisions, Verification Log, Open Loops, Next Action, Status.
- **Archived epic ledger**: `notes/archive/epics/YYYY-MM-DD-<slug>.md`. Completed epic state after explicit archive.
- **Roadmap**: `notes/roadmap.md`. For multi-epic initiatives. Tracks cross-cutting decisions, epic queue, and active epic.
- **Run audit**: `.deepdone/runs/YYYYMMDD-HHMMSS.jsonl`. For loop-mode supervisor traces.
- **`.deepdone/STOP`**: Kill switch. If this file exists, all skills halt immediately.
- **Commit authorization**: Commits only happen in `until-commit`/`end-to-end` modes or on explicit user request. Default is candidate-only.
- **PR/MR creation authorization**: PR/MR drafts are safe by default. Creation and push require explicit approval.
- **Archive authorization**: Archive requires explicit request or supervisor-provided merge/release reference.

## Safety

- Never push, merge, deploy, archive, or run destructive git without explicit approval
- Never `git add .`
- One auto-fix attempt max for verification failures
- Review findings requiring product/architecture judgment always stop for user
