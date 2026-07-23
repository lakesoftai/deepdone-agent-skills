# DeepDone, Agent Loops, and Website Positioning

Status: website messaging brief
Audience: developers evaluating DeepDone
Primary surface: [deepdone.ai](https://deepdone.ai/)
Repository architecture updated: 2026-07-23
Live homepage reviewed: 2026-07-13

## Purpose

This document explains what an agent loop is, how DeepDone relates to that concept, and how the website should describe DeepDone without implying an always-on scheduler, autonomous agent fleet, or deployment platform.

"Loop" has become useful public language for agent products. DeepDone should use it, but always define the loop as bounded, evidence-driven, and developer-triggered. Popularity makes the term easier to recognize, not safe to leave unexplained.

It combines:

- findings from Matt Van Horn's article, [WTF Is a Loop? Peter Steinberger vs. Boris Cherny](https://x.com/mvanhorn/article/2063865685558903149)
- the current DeepDone workflow contract
- a review of the live deepdone.ai homepage on 2026-07-13
- conclusions from discussion about developer-triggered versus scheduled workflows

## Executive conclusion

DeepDone is best described as:

> A developer-triggered, bounded workflow loop for coding agents. One DeepDone skill turns requirements into verified, reviewed local work by choosing the next safe phase, preserving progress in the repository, and stopping at explicit completion or safety boundaries.

Shorter version:

> DeepDone gives coding agents a controlled way to keep working from requirements to a reviewed local commit.

This is clearer than "AI agent skills for automated software delivery" because it explains:

- who starts the work: a developer
- what DeepDone controls: the development workflow
- how it progresses: one verified step at a time
- what it produces: reviewed local work, optionally a local commit
- where it stops: selected mode boundary, blocker, or safety gate

DeepDone does not need a recurring external trigger for its normal use case. A developer provides new requirements and starts one bounded run. Scheduling is optional infrastructure for continuous tasks such as CI monitoring or PR babysitting. It is not part of the core DeepDone value proposition.

## What a loop means

### Concise definition

An agent loop repeatedly:

1. inspects current state
2. chooses the next action
3. performs that action
4. checks the result
5. stops when the goal or a hard boundary is reached, otherwise repeats

```text
goal
  |
  v
inspect state -> choose action -> act -> verify
     ^                              |
     |                              |
     +------ not done or failed ----+
                    |
                    v
             done or hard stop
```

The important part is not repetition. The important part is feedback and control.

A useful loop has:

- a trigger
- a goal
- observable state
- available actions
- verification
- durable memory when work spans sessions
- stopping rules

Without verification, a loop repeats mistakes. Without stopping rules, it can waste time, tokens, and money. Without durable state, interruption forces the agent to rediscover progress.

### Looping and automatic triggering are different

These concepts should not be merged:

| Concept | Meaning |
|---|---|
| Looping | Continue choosing, acting, and verifying until a stop condition is reached. |
| Triggering | Decide when the loop starts. |
| Scheduling | Start the loop automatically at a time or interval. |

A loop can be started by:

- a developer providing new requirements
- a pull request event
- a failed CI check
- a schedule
- another agent or workflow

DeepDone's normal trigger is the first one: a developer provides requirements.

## How DeepDone maps to the loop model

DeepDone already contains the important parts of a bounded agent loop.

| Loop component | DeepDone implementation |
|---|---|
| Trigger | Developer invokes `deepdone` with requirements and a mode. |
| Goal | Requirements, constraints, acceptance criteria, roadmap, and active epic. |
| Decision-maker | `deepdone` inspects repository truth and selects the next internal phase. |
| State | Git state, roadmap, active epic ledger, compact review manifest, private Git review snapshot, status, open loops, and next action. |
| Actions | Eleven narrow internal phases: plan, sync, advance, decide, implement, verify, review, fixup, commit, PR, and archive. |
| Feedback | Tests, verification evidence, skeptical review, exact Git-native review snapshots, and hashed development evidence. |
| Correction | Failed review routes through fixup, verification, and review again. |
| Recovery | Durable ledger state plus the orchestrator's sync phase to reconcile interrupted work. |
| Stopping rules | Mode boundaries, authorization gates, blockers, retry caps, and `.deepdone/STOP`. |

The core path is:

```text
requirements -> plan -> implement -> verify -> review -> commit
                              ^          |
                              |          v
                              +-- fixup -+
```

The full package has more lifecycle steps, but this shorter path explains the main user value.

### The relationship between loops, skills, and phases

A phase and a loop are not the same thing.

> A phase defines how to perform one kind of action. A loop decides which phase to use next, checks the result, and decides whether to continue.

Examples:

- The implement phase knows how to execute the next milestone.
- The verify phase knows how to gather convincing verification evidence.
- The review phase knows how to review the active change set.
- `deepdone` connects those actions into a bounded workflow.

This distinction is central to explaining the product. Internal phases are implementation components. The user-facing product is one public skill controlling the complete workflow.

### How review stays exact without making the agent count files

DeepDone separates code versioning from development state:

- Git stores exact reviewed code as a tree referenced under `refs/deepdone/reviews/<review-id>`.
- Epic ledger and optional roadmap remain development evidence. DeepDone hashes them directly even when Git ignores them.
- Compact local manifest stores Git object IDs, changed-path count, scope roots, and one or two evidence hashes.
- Manifest does not contain one JSON record per changed file.
- Commit asks Git to derive exact paths and must reproduce reviewed tree.

A Git tree is not a Git worktree. It is an internal Git database object, not another checked-out directory or copied project.

This architecture matters for large changes. Whether review covers 12 files or 5,000 files, agent-facing record stays compact. Git handles exact file membership, binary content, deletions, renames, symlinks, and executable modes.

## What DeepDone is and is not

### DeepDone is

- one public skill for structured software work
- one supervisor with eleven narrow internal workflow phases
- developer-triggered by default
- bounded by a selected mode
- stateful through repository artifacts
- recoverable after interruption
- verification-driven
- conservative about commit, push, merge, deploy, archive, and production changes
- usable end to end or one transition at a time

### DeepDone is not

- an always-running background service
- a cron scheduler
- an autonomous issue picker
- a requirement generator
- a multi-agent fleet runtime
- a deployment platform
- a promise that software ships without developer judgment
- an infinite retry mechanism

DeepDone could be called from an external scheduler or event system, but that is an optional integration. It should not define the homepage explanation.

## Recommended website mental model

Use this progression:

```text
You provide requirements
        |
        v
DeepDone checks repository state
        |
        v
Supervisor selects one focused phase
        |
        v
Phase performs one workflow step
        |
        v
DeepDone verifies the result
        |
        +---- more safe work remains ----> repeat
        |
        +---- done, blocked, or gated ----> stop and report
```

The developer remains responsible for requirements and protected decisions. DeepDone removes step-by-step prompting between those boundaries.

## Current website findings

### What already works

The live homepage has several strong elements:

- "Turn requirements into reviewable local commits" names a concrete outcome.
- end-to-end and one-step modes communicate different control levels.
- safety boundaries are visible instead of hidden in documentation.
- installation and quickstart commands are concrete.
- skills are grouped by workflow phase.
- the page consistently avoids claiming automatic push, merge, or deploy.

These should remain.

### Main clarity problems

#### 1. Product category remains unclear

"AI agent skills for automated software delivery" says what market DeepDone belongs to, but not what it actually does.

A visitor still has to infer:

- whether DeepDone is one skill or a collection of phase tools
- whether they must manually choose each phase
- whether "automated" means background or scheduled execution
- whether work continues until deployment
- what role the supervisor plays

Fix: define DeepDone as one public skill running a bounded workflow through focused internal phases.

#### 2. "Loop" appears before it is defined

The page says "Automate the loop" and "Let DeepDone keep moving," but never explains loop mechanics.

This creates the exact confusion found in broader agent-loop discussion. Some visitors will interpret loop as:

- a cron job
- an infinite retry
- background automation
- multiple agents supervising each other
- repeated prompting with no state or verification

Fix: add a plain-language "How DeepDone works" section before modes. Define the bounded loop using five verbs: inspect, choose, act, verify, stop or repeat.

#### 3. "Automate the loop" suggests scheduled autonomy

The intended meaning is bounded end-to-end progression after a developer starts the run. The current heading can imply continuous unattended operation.

Fix: rename it to one of:

- "Run the full bounded workflow"
- "Continue to a reviewed local commit"
- "Let DeepDone handle the next safe steps"

Recommended option: "Continue to a reviewed local commit."

#### 4. Skill cards imply users must choose every phase

Each card says "Use this when..." This weakens the main workflow story and does not match the one-public-skill package.

Normal users should understand:

> Invoke `deepdone` with your requirements. It selects the next focused phase. Request a specific phase through the same skill only when you want manual control over a known workflow stage.

Fix: show one public DeepDone card plus an internal phase map. Present plan, sync, advance, decide, implement, verify, review, fixup, commit, PR, and archive as capabilities, not separate commands.

#### 5. Current site contains a stale run-logging claim

The live Safety section lists:

```text
.deepdone/runs/YYYYMMDD-HHMMSS.jsonl
Supervisor audit trail for looped runs.
```

Current repository documentation and doctor checks reflect removal of run logging. This claim should be removed from the website unless run logging is intentionally restored.

#### 6. "Release" in the hero visual overstates the boundary

The hero control panel shows `PLAN`, `BUILD`, `VERIFY`, and `RELEASE`.

DeepDone's normal end-to-end boundary is a reviewed local commit. Push, merge, deploy, and archive require separate authority or lifecycle actions. "Release" can make the product look broader than its actual contract.

Fix: replace `RELEASE` with `REVIEW` or `COMMIT`.

Recommended sequence:

```text
PLAN | BUILD | VERIFY | REVIEW
```

#### 7. Installation arrives before understanding

The page asks users to install before fully explaining the product model. Technical users can follow the command, but may still not understand why they need the package.

Fix: show the mental model before detailed installation. Keep one primary install CTA in the hero, but move the full installation section below "How it works" and modes.

#### 8. Visual hierarchy favors product name over product meaning

The hero gives most space to "DeepDone Skills." The outcome statement is much smaller. New visitors learn the name before understanding the value.

Fix: make the primary headline outcome-led. Keep DeepDone as brand navigation and eyebrow context.

Screenshot-only visual note: small gray body text and compact uppercase navigation may create readability and contrast risks on the dark background. Confirm with real contrast measurement, keyboard testing, and responsive checks before making accessibility claims.

## Recommended homepage structure

### 1. Hero: outcome and category

Answer three questions immediately:

1. What is DeepDone?
2. What result does it produce?
3. How much control does the developer retain?

### 2. How it works

Show the request-triggered bounded loop. Avoid requiring prior knowledge of "agent loops."

### 3. Two control modes

Compare:

- continue through safe stages to the selected boundary
- perform exactly one transition and return control

### 4. Why it is reliable

Explain:

- durable roadmap and epic ledger
- verification and review feedback
- exact next action
- interruption recovery
- explicit safety and authorization gates

### 5. Install and quickstart

Show one recommended command and one recommended first prompt.

### 6. Workflow phases

Frame these as internal workflow components selected by DeepDone. Show targeted phase requests as advanced usage through the same skill.

### 7. Boundaries and FAQ

State what DeepDone does not do automatically.

## Proposed homepage copy

### Hero

Eyebrow:

> A bounded agent loop for software work

Headline:

> Give your coding agent requirements. Get reviewed local work.

Alternative with stronger commit focus:

> From requirements to a verified local commit.

Supporting copy:

> DeepDone is one agent skill that runs a bounded software workflow. It checks the repository, chooses the next safe phase, preserves progress, verifies changes, and stops when the selected boundary or a blocker is reached.

Proof points:

- Developer-triggered, not always running
- End to end or one safe step at a time
- Durable progress that survives interrupted sessions
- No silent push, merge, deploy, archive, or destructive Git

Primary CTA:

> Install DeepDone

Secondary CTA:

> See how it works

### How it works

Heading:

> One request starts a bounded workflow

Body:

> You provide requirements. DeepDone inspects current repository state and selects the next focused phase. After each step it verifies the result and decides whether to continue, stop, or ask for your judgment.

Definition callout:

> This is the loop: inspect, choose, act, verify, then stop or repeat. You start it with requirements. DeepDone handles the prompts between workflow stages.

### Modes

Section heading:

> Choose how far DeepDone may continue

End-to-end card:

> **Continue to a reviewed local commit**
>
> DeepDone moves through the next safe workflow stages while gates pass. It stops after the authorized local commit, or earlier if verification, review, scope, or authority requires you.

One-step card:

> **Run one safe transition**
>
> DeepDone classifies current state, performs one focused workflow step, records the next action, and returns control.

### Workflow phases section introduction

> Start with DeepDone. It selects the right internal phase for current repository state. Plan, sync, advance, decide, implement, verify, review, fixup, commit, PR, and archive are focused capabilities inside the same skill. Advanced users can request a phase without bypassing state or safety gates.

### Install and quickstart

Recommended command:

```bash
npx skills add lakesoftai/deepdone-agent-skills --skill deepdone
```

Recommended first prompt:

```text
Use $deepdone.
Requirements: <your goal>
Mode: end-to-end.
```

### Safety section

Heading:

> It keeps working only while the evidence and authority allow it

Body:

> DeepDone does not equate activity with progress. Code changes must pass verification and skeptical review. Protected actions require explicit authority. Ambiguous scope, risky decisions, unexplained files, or missing evidence stop the workflow.

## Proposed FAQ

### Who starts DeepDone?

A developer starts DeepDone by providing requirements and selecting a mode. DeepDone is not an always-running background service.

### Do I need a scheduler or recurring trigger?

No. Normal use starts when you provide new requirements. External scheduling is optional for continuous tasks such as CI monitoring or PR babysitting.

### What does "loop" mean here?

DeepDone repeatedly inspects state, chooses one focused internal phase, performs the step, and verifies the result. It stops when the selected boundary is reached or when a safety gate needs developer input.

### Do I need to choose every phase manually?

No. Invoke `deepdone` with your goal. It chooses the right next phase. For manual control over a known workflow stage, request that phase through the same skill. State and authorization gates still apply.

### Does end-to-end mean deployment?

No. DeepDone's end-to-end mode stops after a gated local commit. It does not automatically push, merge, deploy, archive, or change production.

### Does DeepDone run forever until it succeeds?

No. Modes define a bounded target. Verification failures, review findings, ambiguity, missing authority, safety rules, and retry caps can stop the run.

### What happens if work is interrupted?

DeepDone records durable progress in repository roadmaps and epic ledgers. A later run can inspect that state and use the internal sync phase to reconcile recoverable drift.

### Does DeepDone put every reviewed file into a manifest?

No. Git stores exact reviewed code as private local snapshot. Compact manifest stores Git object IDs, path count, scope, and hashes for active ledger and optional roadmap. Agent does not need to read or reason over thousands of path records.

### What is the difference between a loop and a skill?

The public DeepDone skill runs the loop. Each internal phase defines how to perform one kind of workflow action. The loop selects phases, checks their results, and decides whether to continue.

## Messaging rules

### Prefer

- bounded agent loop
- developer-triggered
- bounded workflow
- reviewed local commit
- verified progress
- one focused step at a time
- durable repository state
- recoverable after interruption
- supervisor selects the next phase
- stops at explicit gates

### Avoid or qualify

| Phrase | Risk | Better wording |
|---|---|---|
| automated software delivery | Can imply deployment or unattended delivery. | bounded software workflow for coding agents |
| automate the loop | Can imply scheduling or infinite background work. | run a bounded agent loop |
| autopilot | Implies weak human boundaries. | bounded supervisor |
| runs while you sleep | Not core DeepDone behavior. | continues through authorized stages after you start it |
| release | Exceeds normal local-commit boundary. | review or commit |
| self-healing | Overstates correction guarantees. | verification and review feedback |
| autonomous | Too broad unless bounded immediately. | bounded end-to-end execution |

## Positioning summary

DeepDone should not be marketed as "more autonomy." Many tools make that claim.

Its sharper position is:

> Controlled continuation for coding agents.

Developers already know how to ask an agent to write code. The pain is everything between the requirement and trustworthy completion:

- deciding what comes next
- preserving state when sessions end
- verifying changes
- reviewing before integration
- fixing clear findings without expanding scope
- stopping when judgment or authority is required

DeepDone packages that control loop into one reusable skill and durable repository state.

## Recommended first website changes

1. Replace the hero category and headline with the proposed bounded-agent-loop positioning.
2. Add "One request starts a bounded workflow" before installation and modes.
3. Rename "Automate the loop" to "Continue to a reviewed local commit."
4. Replace separate skill cards with one DeepDone card and an internal phase map.
5. Remove the stale `.deepdone/runs` claim.
6. Change `RELEASE` in the hero visual to `REVIEW` or `COMMIT`.
7. Add FAQ answers for triggering, scheduling, loop meaning, and end-to-end boundaries.

## Source of truth

Website claims should remain aligned with:

- [README](../README.md)
- [DeepDone](../skills/deepdone/SKILL.md)
- [Workflow contract](../skills/deepdone/references/state-machine.md)
- [Safety and modes](../skills/deepdone/references/safety-and-modes.md)

When website wording conflicts with those files, repository contract wins.
