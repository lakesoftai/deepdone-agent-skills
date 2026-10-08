# Decide Phase

## Purpose

Resolve one consequential requirement or interface choice from evidence. Ask only for a remaining decision that needs the user's judgment or authority.

## Source Priority

Use sources in this order:

1. repo code and existing conventions
2. official docs and specs
3. version-aware MCP documentation sources
4. narrow ecosystem sources only when official docs are incomplete

Do not lead with blogs unless nothing better exists.

## Preconditions

- a selected epic ledger or compact task record exists
- decision question is concrete
- repo constraints are known

For a compact task, follow the [task contract](task-contract.md), retain its selector, and record a consequential choice in existing Open Loops or constraints. Do not add an epic Decisions section.

## Resolve Facts Before Questions

Read established user requirements and decisions, the selected work unit, relevant callers, tests and repository conventions. Inspect repository-answerable facts directly. Do not reopen settled choices or ask the user to locate facts available in the repository.

If that evidence fixes the answer, follow it. Routine, low-risk implementation choices follow existing conventions within the admitted scope; they need no questionnaire, alternatives exercise or specialist call.

## Unresolved Product Behavior

When an unanswered question changes externally visible behavior, describe the concrete scenario, unresolved choice and consequence. Ask one focused question, with a recommendation when supported. For example: "A request repeats the same idempotency key with a different payload. Should it return the original result or reject the mismatch? I recommend rejection so callers cannot mistake an unapplied payload for success."

Keep the disputed semantics pending until the answer arrives. Record the exact question and next action; do not encode a recommendation as an accepted requirement. Continue independent, settled work only when existing routing, scope and mode permit it. An unresolved future choice must not prevent current applicable verification.

## Consequential Interface Choices

For an interface choice costly to reverse, compare two materially different viable designs unless an existing contract already fixes the answer. Use concrete caller examples to explain invariants, failure modes, testability and compatibility or migration cost. Include operational cost or rollback impact where relevant. Recommend one and explain the decisive tradeoff; do not manufacture alternatives or require an exhaustive design exercise.

Distinguish an authorized technical choice from a product or architecture decision still requiring the user. A recommendation grants no additional action authority. If authority is missing, present the recommendation and focused decision question, then leave dependent work pending.

## Ledger Writeback

For a resolved consequential epic choice, append a compact block under `## Decisions` (omit inapplicable fields):

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

Pending decisions belong in existing Open Loops with the exact question and Next Action. Once resolved, update the existing requirements or constraints, retain the selected task or epic, and resume through current routing, verification and review rules. Preserve STOP, mode boundaries, consumed budgets and existing authority limits; answering a question resets none of them.

## Workflow

1. Frame the exact unresolved choice and inspect available facts and prior decisions.
2. Resolve facts directly; use primary sources only where a remaining factual gap requires them.
3. For consequential product ambiguity, ask the focused scenario question. For a costly interface choice, compare substantive designs and recommend one.
4. Decide within existing authority, or keep the question pending for the user. Do not implement disputed semantics.
5. Record the consequential outcome, implementation constraints and verification impact in the selected work unit. Record roadmap impact only when genuinely cross-epic.
6. Update `Next Action` and return the inspected decision through existing transient routing context: analysis still needed, user answer required, future choice, or resolved. Do not reset prior outcomes or budgets.

## Output

Return the resolved choice and its reason, or the exact pending question and recommendation. Include alternatives and concrete implementation implications only when relevant. State which work can proceed within the current mode and which work must wait.
