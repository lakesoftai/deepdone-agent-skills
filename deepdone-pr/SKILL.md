---
name: DeepDone PR
slug: deepdone-pr
description: Prepare a platform-neutral pull or merge request draft, optionally create it only with explicit approval and clear repository tooling, and inspect CI for an existing PR when asked.
---

# DeepDone PR

## Purpose

Bridge completed local DeepDone work to a review request without assuming GitHub, GitLab, push permission, or merge authority.

This skill prepares PR/MR material by default.
It creates or inspects a PR only when the user or supervisor context explicitly asks for that exact step.

Never push by default.
Never merge.
Never deploy.

## Inputs

The user or supervisor may ask for:

- PR draft only
- actual PR creation
- CI or check inspection for an existing PR
- PR body refresh after commit or review changes

Prefer explicit PR URL, PR id, or remote platform when provided.

If the request says "PR", treat that as pull request or merge request depending on repo host.

## Preconditions

Before drafting, inspect:

- `git status --short --untracked-files=all`
- current branch
- latest commit message or commit candidate
- active roadmap if present
- active epic ledger
- latest `Verification Log`
- latest `review-result`
- `Open Loops`

Before actual PR creation, all must be true:

- user explicitly requested creation
- branch name and target branch are clear
- remote host is clear
- current branch is published or user explicitly approved push
- repo-native tool is available and authenticated
- PR title/body accurately reflect the local commit and DeepDone state
- no unresolved open loop blocks review

If any precondition is missing, stop with a draft and exact blocker.

Before CI inspection, require one of:

- explicit PR URL or id
- repo tooling can clearly identify the current branch PR

## PR Draft Shape

Use this platform-neutral body:

```md
## Summary

- <what changed>

## DeepDone

- Epic: <name or none>
- Ledger: <path or none>
- Milestone: <name or scope>
- Review: <review-result or not found>

## Verification

- command: `<command>`
  result: pass|fail|blocked
  notes: <notes>

## Open Loops

- none | <remaining risk or follow-up>
```

Keep title imperative and under 72 characters when practical.
Use the commit subject when it is accurate.

## Platform Handling

Stay platform-neutral by default.

If platform tooling is clearly available, use repo-native commands only as an implementation detail:

- GitHub examples: `gh pr create`, `gh pr checks`
- GitLab examples: `glab mr create`, `glab mr checks`

Do not assume either tool exists.
Do not install tools.
Do not push unless the user explicitly asks and safety checks pass.

## Workflow

1. Inspect git, commit, roadmap, ledger, verification, review, and open loops.
2. Determine mode: draft only, create PR, or inspect CI.
3. Build or refresh title and body.
4. If draft only, return draft and next steps.
5. If create requested, verify all creation preconditions.
6. Create PR only when authorized and tooling is clear.
7. If CI requested, inspect only the identified PR.
8. Report blockers, CI failures, and next action.

## Output

Return:

- mode: draft | create | ci
- title
- body
- platform or unknown
- creation or CI result if requested
- blockers
- next action
