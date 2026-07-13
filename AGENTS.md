# DeepDone Skills

Agent-driven workflow management for software projects. Two public skills expose the workflow. `deepdone-orchestrate` routes between bundled internal phases.

## Skills

| Skill | Role |
|---|---|
| `deepdone-orchestrate` | Supervisor: classifies state, loads one internal phase, enforces mode budgets and safety gates |
| `deepdone-advance` | Move multi-epic initiative to next queued epic |

Internal orchestrator phases are plan, sync, decide, implement, verify, review, fixup, commit, PR, and archive. They live as one-level reference modules under `deepdone-orchestrate`; they are not selector-visible skills.

## Workflow

```text
requirements -> plan -> sync -> advance -> decide -> implement -> verify -> review -> fixup -> commit -> pr -> archive
                       ^                                      |
                       +------ resume loop after state drift --+
                                                         ^                 |
                                                         +-- review loop --+
```

The orchestrator (`deepdone-orchestrate`) drives this state machine. It inspects repo state, classifies the current position, and loads exactly one matching internal phase.

`pr` and `archive` are post-commit lifecycle steps. They are not automatic side effects of commit:

- The PR phase drafts PR/MR text by default. Creation requires explicit approval plus clear remote, target branch, branch publish state, and repo-native tooling.
- The archive phase moves completed epic state only after explicit current-run archive authority plus a clear merge or release reference.

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
Use $deepdone-orchestrate.
Requested phase: PR.
Prepare a PR/MR draft for the current DeepDone work.
```

For completed work archival:

```
Use $deepdone-orchestrate.
Requested phase: archive.
Archive <ledger path> after merge/ref <PR URL, merge SHA, or release tag>.
```

## Key Concepts

- **Epic ledger**: `notes/epics/YYYY-MM-DD-<slug>.md`. Standard sections: Summary, Constraints, Milestones, Decisions, Verification Log, Review, Open Loops, Next Action, Status.
- **Archived epic ledger**: `notes/archive/epics/YYYY-MM-DD-<slug>.md`. Completed epic state after explicit archive.
- **Roadmap**: `notes/roadmap.md`. For multi-epic initiatives. Tracks cross-cutting decisions, epic queue, and active epic.
- **Reviewed change set**: Latest passing Review records exact paths plus ignored deterministic evidence under `.deepdone/reviews/`. Commit may include only that unchanged set.
- **`.deepdone/STOP`**: Kill switch. If this file exists, all skills halt immediately.
- **Commit authorization**: Commits only happen in `until-commit`/`end-to-end` modes or on explicit user request. Default is candidate-only.
- **PR/MR creation authorization**: PR/MR drafts are safe by default. Creation and push require explicit approval.
- **Archive authorization**: Archive requires explicit current-run user authority. Merge or release evidence never grants authority.
- **Advance gate**: Reviewed paths must be clean before next epic activation. No automatic stash, reset, discard, or abandonment.

## Safety

- Never push, merge, deploy, archive, or run destructive git without explicit approval
- Never `git add .`
- One auto-fix attempt max for verification failures
- Review findings requiring product/architecture judgment always stop for user
