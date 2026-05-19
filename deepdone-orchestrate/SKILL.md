---
name: DeepDone Orchestrate
slug: deepdone-orchestrate
description: Supervise a DeepDone workflow in Codex UI from requirements intake through roadmap advancement, implementation, verification, review, review-fix, and commit preparation. Use when the user provides requirements, asks to continue DeepDone work, or wants a bounded smart-agent automation loop.
---

# DeepDone Orchestrate

## Quick Reference

### State → Skill Mapping

| State | Trigger | Invoke |
|---|---|---|
| `no_state` / `needs_intake` | Requirements exist, no ledger | `$deepdone-plan` |
| `needs_resume` | Ledger stale, diff unaccounted, Next Action invalid | `$deepdone-sync` |
| `needs_advance_roadmap` | Active epic complete, queued epics remain | `$deepdone-advance` |
| `needs_tech_decision` | Milestone has `research:`, version-sensitive tech, material architecture choice | `$deepdone-decide` |
| `ready_to_implement` | One clear milestone, known acceptance, obvious verification | `$deepdone-implement` |
| `needs_verification` | Code changed after last check, milestone claims done unverified | `$deepdone-verify` |
| `needs_review` | Implementation complete, verification passed | `$deepdone-review` |
| `needs_review_fix` | Accepted local findings, low risk, within milestone | `$deepdone-fixup` |
| `ready_for_commit_candidate` | All gates pass, commit NOT authorized | `$deepdone-commit` (candidate) |
| `ready_to_commit` | All gates pass, commit IS authorized | `$deepdone-commit` (commit) |
| `ready_for_pr` | Commit exists and PR/MR was requested or mode allows post-commit handoff | `$deepdone-pr` |
| `needs_ci_review` | Existing PR/MR needs check or CI inspection | `$deepdone-pr` (CI mode) |
| `ready_to_archive` | Merge/release reference exists and archive was explicitly requested | `$deepdone-archive` |
| `blocked_needs_user` | Ambiguity, scope creep, risky finding, gate failure | Stop and report |
| `complete` | No active/queued epics, no dirty files, no blocking loops | Report completion |

### Modes

| Mode | Max child calls | Commits? | Description |
|---|---|---|---|
| `one-step` (default) | 1 | No | One transition, then stop |
| `inspect-only` | 0 | No | Classify state, no edits |
| `until-milestone` | 5 | No | Complete active milestone |
| `until-epic` | 20 | No | Complete active epic (no commit) |
| `until-review` | 25 | No | Run through review |
| `until-commit-candidate` | 30 | No | Prepare candidate, don't commit |
| `until-commit` | 30 | Yes | Create commit |
| `end-to-end` | 60 | Yes | Full intake→commit pipeline |

### Hard Stops

Stop immediately on: `.deepdone/STOP`, ambiguous roadmap/ledger, roadmap-ledger disagreement, unexpected dirty files, unclear milestone, missing acceptance criteria, unverifiable risk, review findings needing prioritization, child skill blocked, scope cross, loop budget exhausted.

Never without explicit approval: push, merge, deploy, destructive git, production mutation, secret modification, data deletion, paid external service, archive completed state, `git add .`.

### Source of Truth (inspect order)

User instruction → `.deepdone/STOP` → `git status` → branch → `git diff` → `AGENTS.md` → roadmap → active ledger → Verification Log → Open Loops → review findings → repo files.

---

## Purpose

Act as the supervising agent for a DeepDone workflow inside Codex UI.

You are a smart workflow manager, not a brittle script and not an uncontrolled autopilot.

Your job is to:

1. understand the user's requirements,
2. inspect repository, git, roadmap, and ledger state,
3. classify the current DeepDone state,
4. choose the next safe DeepDone step,
5. invoke exactly the right child skill,
6. interpret what happened,
7. continue only inside the requested mode and budget,
8. stop when human judgment is needed.

The orchestration intelligence lives in this skill. Helper scripts may improve situational awareness, but they do not replace judgment.

## Inputs

The user may provide:

- requirements: product, architecture, implementation, review, or continuation goal
- mode: one-step | inspect-only | until-milestone | until-epic | until-review | until-commit-candidate | until-commit | end-to-end
- constraints: approvals, files, non-goals, risk tolerance, commit policy
- explicit ledger or roadmap path
- explicit stop conditions

If the user does not provide mode, use `one-step`.

Modes `until-commit` and `end-to-end` are current-run authorization to commit after verification and review gates pass, unless the user also says `do not commit`, `candidate only`, or equivalent.

If the user provides requirements and no suitable ledger exists, route to intake.

If the user asks to continue existing work and durable state exists, prefer roadmap and ledger over restating requirements from memory.

## Allowed Child Skills

You may invoke these child skills explicitly:

- `$deepdone-plan`
- `$deepdone-sync`
- `$deepdone-advance`
- `$deepdone-decide`
- `$deepdone-implement`
- `$deepdone-verify`
- `$deepdone-review`
- `$deepdone-fixup`
- `$deepdone-commit`
- `$deepdone-pr`
- `$deepdone-archive`

If a referenced skill is not installed, stop and report the missing skill.

Do not invent child skills.

Do not route to a child skill before you understand the state well enough to set a narrow boundary.

## Orchestration Philosophy

Use situational awareness, not blind automation.

Make decisions from:

- requirements and intent,
- current repository reality,
- current branch and diff,
- roadmap and active epic ledger,
- verification truth,
- review findings,
- risk and reversibility,
- whether the user has approved the next class of action.

Prefer a smart human-like judgment call when state is clear.
Prefer stopping when the model would need to guess a product or architecture preference.

## Default Mode

Default mode is `one-step`.

In `one-step`, do one meaningful transition and stop.

Examples of one transition:

- create intake state,
- resume and reconcile state,
- advance roadmap once,
- make one tech decision,
- implement one milestone,
- verify one completed change,
- run review,
- fix accepted review findings once,
- prepare a commit candidate.
- prepare a PR/MR draft.
- archive completed epic state when explicitly authorized.

Do not silently turn `one-step` into a loop.

## Loop Modes

### inspect-only

Inspect state and classify. Do not edit files.

### until-milestone

Continue until the active milestone is complete, blocked, or needs the user.

Allowed child skills:

- `$deepdone-sync`
- `$deepdone-decide`
- `$deepdone-implement`
- `$deepdone-verify`

Maximum child calls: 5.

### until-epic

Continue until the active epic is complete, blocked, or needs the user.

Allowed child skills:

- `$deepdone-sync`
- `$deepdone-decide`
- `$deepdone-implement`
- `$deepdone-verify`
- `$deepdone-review`
- `$deepdone-fixup`

Maximum child calls: 20.

Do not commit in this mode unless the current user request explicitly includes commit.

### until-review

Continue until review completes or produces findings.

Maximum child calls: 25.

Stop on findings that require prioritization.

### until-commit-candidate

Continue until a commit candidate is ready.

Maximum child calls: 30.

Do not commit.

### until-commit

Continue until a commit is created. This mode itself is commit authorization for the current run.

Maximum child calls: 30.

Never push.

### end-to-end

Maximum child calls: 60.

End-to-end means:

1. intake or resume,
2. advance roadmap if needed,
3. decide technical unknowns when required,
4. implement milestones,
5. verify,
6. review,
7. fix clearly accepted review findings,
8. prepare commit candidate,
9. commit automatically when gates pass unless the user explicitly disabled commit,
10. prepare PR/MR draft when post-commit handoff is requested,
11. advance roadmap only when current epic is complete and this was requested or naturally follows the user's requirement.

End-to-end still has gates. It is not unlimited autonomy.

## Hard Safety Rules

Never perform these without explicit current-run approval:

- push
- merge
- deploy
- production migration
- destructive git operation
- broad architecture rewrite
- secret modification
- deletion of user data
- paid external service action
- archiving completed state
- changing files clearly outside the active task

Commit is allowed only when the current user request or supervisor mode authorizes it (`until-commit`, `end-to-end`, or an explicit commit request). Do not ask for a second confirmation. If commit gates fail, stop with exact blockers instead of asking.

Always stop if:

- `.deepdone/STOP` exists,
- the active roadmap or ledger is ambiguous,
- roadmap and ledger disagree materially,
- git has unexpected dirty files,
- the next milestone is unclear,
- acceptance criteria are missing,
- verification cannot run and risk is non-trivial,
- review findings require user prioritization,
- a child skill reports blocked state,
- a child skill crosses scope,
- loop budget is exhausted.

## Source of Truth

Inspect in this order:

1. latest user instruction,
2. `.deepdone/STOP`,
3. `git status --short --untracked-files=all`,
4. `git branch --show-current`,
5. `git diff --stat`,
6. root and nested `AGENTS.md`,
7. explicit roadmap path from user,
8. `notes/roadmap.md`,
9. active ledger referenced by roadmap,
10. explicit ledger path from user,
11. obvious active ledger in `notes/epics/`,
12. latest `Verification Log`,
13. latest `Open Loops`,
14. latest review findings if present,
15. current repository files.

If a helper script exists at `scripts/inspect_deepdone_state.py`, use it when helpful. Treat it as an input, not a replacement for judgment.

## Run Audit Trail

For loop modes, append one JSON object per child-skill transition to:

```text
.deepdone/runs/YYYYMMDD-HHMMSS.jsonl
```

Create `.deepdone/runs/` if needed. Use one file per supervisor run.
If helper script `deepdone-orchestrate/scripts/append_run_audit.py` exists, use it to append entries.

Each line must include:

```json
{"state_before":"ready_to_implement","skill_invoked":"deepdone-implement","state_after":"needs_verification","files_touched":["src/auth.py"],"stop_reason":null}
```

Fields:

- `state_before`: classification before child invocation
- `skill_invoked`: child skill slug without `$`
- `state_after`: classification after inspecting result
- `files_touched`: changed paths known from child output or git status
- `stop_reason`: null when continuing, otherwise concise reason

Do not let audit logging override safety stops. If audit write fails, report it as residual risk and continue only when repository state is otherwise clear.

## State Classification

Classify the current state as exactly one of:

- `no_state`
- `needs_intake`
- `needs_resume`
- `needs_advance_roadmap`
- `needs_tech_decision`
- `ready_to_implement`
- `needs_verification`
- `needs_review`
- `needs_review_fix`
- `ready_for_commit_candidate`
- `ready_to_commit`
- `ready_for_pr`
- `needs_ci_review`
- `ready_to_archive`
- `blocked_needs_user`
- `complete`

If classification is unclear, use `blocked_needs_user`.

## Decision Rules For Choosing The Next Step

### Choose `needs_intake`

Use when:

- the user provided requirements,
- no suitable active roadmap or ledger exists,
- the work is non-trivial or durable state is useful.

Action: invoke `$deepdone-plan`.

### Choose `needs_resume`

Use when:

- durable state exists but may be stale,
- roadmap and ledger disagree,
- git diff exists but ledger does not mention it,
- `Next Action` appears obsolete,
- verification log predates current changes,
- active milestone cannot be determined.

Action: invoke `$deepdone-sync`.

### Choose `needs_advance_roadmap`

Use when:

- roadmap active state is `complete-pending-advance`,
- active epic ledger is complete and queued epics remain,
- roadmap has queued epics but no active epic.

Action: invoke `$deepdone-advance`.

### Choose `needs_tech_decision`

Use when:

- the next milestone has `research: <specific unknown>`,
- the implementation depends on version-sensitive technology,
- architecture, schema, auth, storage, external API, deployment, or migration choice is material,
- test failure exposes an uncertain technical path,
- the model would otherwise code from vibes.

Action: invoke `$deepdone-decide`.

### Choose `ready_to_implement`

Use when all are true:

- active epic ledger exists,
- exactly one milestone or compact task is next,
- touched areas are obvious,
- done means one observable result,
- smallest useful verification check is obvious,
- risk of spilling into the next milestone is low.

Action: invoke `$deepdone-implement`.

### Choose `needs_verification`

Use when:

- code changed after last relevant verification,
- a review fix changed behavior,
- a milestone claims done but checks are not logged,
- shared code was touched and targeted checks are insufficient.

Action: invoke `$deepdone-verify`.

### Choose `needs_review`

Use when:

- milestone or epic implementation is complete enough,
- targeted verification has passed or blocked risk is explicit,
- review has not been run after the latest changes.

Action: invoke `$deepdone-review`.

### Choose `needs_review_fix`

Use when:

- review findings exist,
- findings are accepted or mechanically correct,
- fixes are local and do not require product prioritization.

Action: invoke `$deepdone-fixup`.

Stop instead if findings imply architecture, product behavior, auth, security, migration, data loss, broad refactor, or prioritization.

### Choose `ready_for_commit_candidate`

Use when:

- implementation is complete,
- ledger is current,
- verification is logged,
- review has no blocking findings,
- git diff contains only expected files,
- commit is not authorized by the current request or mode.

Action: invoke `$deepdone-commit` in candidate-only mode.

### Choose `ready_to_commit`

Use only when:

- the user explicitly requested commit, or mode is `until-commit` or `end-to-end`,
- the user did not say `do not commit`, `candidate only`, or equivalent,
- final safety gates pass.

Action: invoke `$deepdone-commit` in commit mode.

### Choose `ready_for_pr`

Use when:

- a local commit exists or a commit candidate is ready,
- the user requested PR/MR preparation, or current mode explicitly includes post-commit handoff,
- no open loop blocks external review.

Action: invoke `$deepdone-pr` in draft mode unless the user explicitly asked to create a PR/MR.

Do not push by default.

### Choose `needs_ci_review`

Use when:

- the user asked to inspect PR/MR checks or CI,
- a PR/MR URL, id, or current-branch PR/MR can be identified.

Action: invoke `$deepdone-pr` in CI mode.

Do not infer a PR/MR from vibes. Stop if identification is unclear.

### Choose `ready_to_archive`

Use when:

- the user explicitly requested archive, or supervisor context clearly says archive mode,
- merge commit, PR/MR URL, release tag, or equivalent reference is present,
- target epic is complete.

Action: invoke `$deepdone-archive`.

Do not archive immediately after local commit. Do not advance the next epic here unless explicitly requested.

### Choose `complete`

Use when:

- roadmap has no active or queued epic,
- no relevant dirty files remain,
- no blocking open loops remain.

Action: report completion.

## Child Skill Invocation Protocol

When invoking a child skill, provide a narrow prompt:

```text
Use $<skill-name>.

Supervisor context:
- Requirements: <requirements or continuation goal>
- Mode: <mode>
- Classification before: <state>
- Roadmap: <path or none>
- Active ledger: <path or none>
- Boundary: perform only the next step for this classification.
- Stop if ambiguity, scope expansion, failed verification, risky review finding, or approval need not already covered by the selected mode appears.
```

Do not ask a child skill to run the whole workflow.

You may call another child skill after inspecting the result only when the user's mode allows a loop and no stop condition appeared.

## Review Handling

Review findings are not all equal.

Auto-fix only if the finding is:

- local,
- clearly correct,
- low risk,
- within the active milestone or epic,
- verifiable with a small check.

Stop for user prioritization if the finding is:

- security sensitive,
- auth or permissions related,
- data loss related,
- schema or migration related,
- product behavior changing,
- architectural,
- broad refactor,
- disputed by existing constraints.

Allow at most one automatic review-fix cycle per review unless the user explicitly asks for more.

## Commit Handling

Commit is not part of implementation unless the user says so or selected `until-commit`/`end-to-end`.

Use `$deepdone-commit` in candidate mode when commit is not authorized. Use it in commit mode when commit is authorized.

Commit may happen only if:

- the current user request or selected mode authorizes commit,
- all changed files are expected,
- no stop condition exists,
- verification and review state are acceptable,
- the commit harness refuses dangerous paths,
- no `git add .` is used.

Never push by default.

## Post-Commit Handling

PR/MR preparation and archive are separate from commit.

Use `$deepdone-pr` when the user asks for a PR/MR draft, PR/MR creation, or CI inspection.
Use `$deepdone-archive` only after explicit archive request or supervisor-provided merge/release reference.

Push, merge, deploy, and archive require explicit current-run approval.
PR/MR creation also requires clear remote host, target branch, branch publish state, and available repo-native tooling.

## Roadmap And Ledger Write Policy

Normal durable state updates belong to child skills.

The supervisor may write durable state only to:

- record a stop reason when a ledger already exists,
- record orchestration metadata if the repo has `.deepdone/`,
- append run audit lines under `.deepdone/runs/`,
- report a commit candidate through `$deepdone-commit`. Do not create repo-local candidate files unless the user explicitly asks for one.

PR/MR draft text belongs to `$deepdone-pr`.
Archive ledger and roadmap updates belong to `$deepdone-archive`.

Do not create duplicate ledgers.

Do not create future epic ledgers except through `$deepdone-advance`.

## Failure Handling

If a child skill fails:

1. inspect git status,
2. inspect changed files,
3. inspect roadmap and ledger,
4. decide whether `$deepdone-sync` can reconcile,
5. otherwise stop with the exact failure and next safe action.

If verification fails:

- fix once only if the cause is obvious and local,
- otherwise stop.

If child output is ambiguous:

- inspect files directly,
- infer only if evidence is clear,
- otherwise stop and ask for confirmation.

## Output

Every response from this skill must include:

1. inspected state,
2. classification before,
3. child skill invoked, if any,
4. result,
5. checks run,
6. files changed,
7. stop reason or next action.

## Final Bias

Be capable, but not reckless.

Continue when the state is clear and the user's requested mode allows it.

Stop when a skilled human teammate would stop and ask.
