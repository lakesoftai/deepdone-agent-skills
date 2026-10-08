# Compact Task Contract

A small task uses one durable `.deepdone/tasks/<task-id>.md` record. It has no epic, roadmap, milestone list, or companion planning files. Keep the record at its original path after completion. Its ID is `[a-z0-9][a-z0-9_-]{0,79}` and matches the filename stem; no symlink component is supported. Never reuse an ID for a different task.

## Record

Plan writes exactly one `Task` section containing one strict JSON block:

```json
{
  "schema": 1,
  "kind": "task",
  "id": "fix-calculator",
  "goal": "Add subtraction while preserving addition",
  "scope": {"include": ["src/calc.py", "tests/test_calc.py"], "exclude": []},
  "acceptance": [{"check_id": "arithmetic", "condition": "Addition and subtraction return the expected results"}],
  "constraints": ["Keep the existing API"]
}
```

Also write one each of `Verification Log`, `Review`, `Open Loops`, `Next Action`, and `Status`. Initialize Review as pending, Status as active, Open Loops as none, and Next Action as the concrete implementation step. The verification wrapper adds `Verification Contract` later. Missing or duplicate structural sections, duplicate JSON keys, unknown fields/schema, empty goal/scope/acceptance, malformed types and mismatched IDs block. Constraints may be empty. Status is exactly `active`, `blocked`, or `complete`.

Every acceptance pair has a unique intended check ID and a nonempty condition. On inventory initialization/revision and every readiness gate, it must match a current required check whose `acceptance` text equals that condition exactly. Additional required/advisory checks are allowed; advisory checks cannot discharge acceptance. Changing a condition requires a revised definition and genuine execution under its new digest. Historical definitions and receipts remain structurally validated under their original declarations. Matching text binds declarations; Review still judges semantic coverage.

Review scope must equal the task's normalized include/exclude sets. Ordering is insignificant; duplicates and silent scope changes block. Revise the task before obtaining a new review capture when scope legitimately changes.

## Selection

Use the shared `work_unit.py` descriptor through inspection and downstream helpers. Pass exactly one typed selector, `--task <path>` or `--ledger <epic-path>`. Verification, capture and committed-work checks require explicit selection. Inspection and candidate/commit may discover a unit. Inspection also accepts its existing optional positional repository root.

Without explicit selection, active/blocked tasks and epics compete equally. Multiple candidates block with paths; a roadmap cannot override a competing task. Broken pointers or malformed candidates block rather than trigger fallback. An explicit independent valid unit avoids incidental unreadable unselected records. Unknown dirty-code ownership still blocks; never create a convenient new task to claim it.

Completed tasks are historical and excluded from automatic selection. Do not revalidate their old receipts/source/cwd during discovery or automatically reopen them. Existing reviewed-complete fallback is epic-only. Pin the selected selector across every phase, including the task's transition to complete. A later run must explicitly name a completed task to revalidate it. Generic outputs report kind, display ID, path, title, status and path-derived identity, plus selection source/errors. Task output never invents an epic or milestone.

## Lifecycle

- Plan creates the compact record before implementation.
- Implement and Fixup keep it active, update existing sections, append pending Review after changes, and route to Verify. Use Open Loops for decisions; do not add a Decisions or Milestones section.
- Verify establishes current readiness and sets Next Action to Review. It does not complete the task.
- Review pass owns Status complete. Finish Next Action and all other record writes before capture. Use only `evidence.ledger: <task-path>`; no unrelated roadmap evidence. Capture failure makes the pass non-actionable and records a newer pending/blocked result.
- Candidate-only does not stage or commit. Authorized commit uses the same exact snapshot, ownership and authority gates and stops immediately afterward. Never change captured task bytes to mark a commit.
- A later `check_reviewed_change_set.py --task <path>` is a read-only committed-task boundary. It checks receipts, source, context, snapshot, HEAD and evidence. Status complete proves review completion only; it does not prove integration. Inspection reports those outcomes separately.

Retain the task, manifest and private review ref. Tasks never Advance or Archive, and `--cleanup-after-advance` is rejected. Requested task Advance/Archive stops with an unsupported-lifecycle explanation before any write. A task has no roadmap association and must not modify an unrelated epic's roadmap.

Legacy mode names remain compatible: `until-milestone` stops after the single task's verification, `until-epic` after its review. One-step, inspect-only, until-review and commit-mode budgets/authority are unchanged. These names do not create an epic or milestone.

## Evidence and compatibility

Inventory/receipt schema remains 1; review manifest remains 2. `ledger`, `ledger_path`, and role `ledger` are existing wire names for the selected durable record. `work_unit` in receipts remains SHA256 of the canonical relative path, unchanged for epics. CLI descriptor `work_unit.identity` exposes that digest separately from the human ID.

Task records require typed headers, receipts and exact snapshots from introduction. They never use legacy pre-receipt fallback, even after header/contract removal or rename. Do not rewrite existing epic or task history.

All canonical task records are local development evidence, including unignored or staged records. Staged evidence remains unowned and blocks actual commit. Fingerprints skip recognized task files and the incidental `.deepdone/tasks` container entry, but still visit ordinary children. This is not a subtree exclusion: ordinary files/empty directories and explicitly declared source roots retain exact Git materialization gates. Task evidence updates do not invalidate source fingerprints; post-capture task edits invalidate the direct evidence hash. If a source projection changes, genuinely rerun checks instead of rewriting receipts.
