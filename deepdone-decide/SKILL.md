---
name: DeepDone Decide
slug: deepdone-decide
description: Research unknown or version-sensitive technology with official sources first, compare realistic options, and record one compact decision block in epic ledger. Use when implementation depends on a technical choice.
---

# DeepDone Decide

## Purpose

Make one technical choice with evidence, not vibes.

## Source Priority

Use sources in this order:

1. repo code and existing conventions
2. official docs and specs
3. version-aware MCP documentation sources
4. narrow ecosystem sources only when official docs are incomplete

Do not lead with blogs unless nothing better exists.

## Preconditions

- active epic ledger exists
- decision question is concrete
- repo constraints are known

If ledger does not exist and task is too small for one, keep decision in thread and stay brief.

## Compare Real Options

For meaningful unknowns, compare at least two plausible options unless current stack already hard-locks one answer.

Check:

- fit with current stack
- migration cost
- operational cost
- testability
- failure modes
- lock-in
- rollback impact

## Ledger Writeback

Append compact block under `## Decisions`:

```md
### YYYY-MM-DD: <decision title>

- Question: ...
- Chosen: ...
- Why: ...
- Rejected: ...
- Implementation notes: ...
- Verification impact: ...
- Sources: ...
```

If the decision constrains more than the active epic, also append a compact summary under roadmap `## Cross-Cutting Decisions`:

```md
- YYYY-MM-DD: <decision title>
  - scope: epics affected or whole initiative
  - chosen: ...
  - reason: ...
  - source ledger: notes/epics/YYYY-MM-DD-<slug>.md
```

Do not duplicate ordinary milestone-local choices into the roadmap.

## Workflow

1. Frame exact decision question.
2. Extract repo constraints from code, AGENTS, and task.
3. Gather primary sources first.
4. Force options set.
5. Choose one answer.
6. Record rejected options and why they lost.
7. Translate decision into implementation constraints and verification impact.
8. Record cross-epic impact in roadmap when the choice constrains later epics.
9. Update `Next Action` if decision changes sequence.

## Output

Return:

- chosen option
- why it wins here
- rejected options
- concrete implementation implications
