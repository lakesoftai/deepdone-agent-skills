# Verification execution contract

Readiness requires captured executions for an explicit current inventory. The
wrapper is `scripts/verification.py` beside the phase helpers. It uses Python's
standard library on POSIX systems with `flock`, process groups, and atomic rename.
It is local evidence, not a sandbox, signature service, or general run logger.

## Declare, run, validate

Write a JSON array of checks to a local file, then invoke the helper from the
repository root (replace `$SCRIPT` with the installed helper path):

```sh
python3 "$SCRIPT" init --ledger notes/epics/demo.md --inventory /tmp/checks.json --reason 'Declare acceptance checks for this epic'
python3 "$SCRIPT" run --ledger notes/epics/demo.md --check-id unit --purpose readiness
python3 "$SCRIPT" check --ledger notes/epics/demo.md
```

Example inventory entry, to adapt to the actual repository:

```json
[{
  "id": "unit",
  "acceptance": "Changed package behavior and its regression tests pass",
  "required": true,
  "argv": ["/usr/bin/python3", "-B", "-m", "unittest", "discover", "-s", "tests"],
  "cwd": ".",
  "inputs": [
    {"path": "src", "role": "source"},
    {"path": "tests", "role": "source"},
    {"path": "pyproject.toml", "role": "source"}
  ],
  "exclusions": [],
  "env": {"PYTHONDONTWRITEBYTECODE": "1"},
  "context": "local-files",
  "timeout": 120
}]
```

The `run` exit status describes that execution; use `check` and the consuming
gates to determine whole-inventory readiness.

Use actual discovered wrappers, configuration, fixtures, discovery directories,
and acceptance conditions. The helper proves execution and applicability; Review
must judge check sufficiency. A trivial successful command is not acceptance proof.
Declare an explicit generated-cache exclusion as `{"path":"src/cache",
"reason":"Disposable generated output"}` only when justified. Exclusions are
literal descendants of declared roots and cannot cover another designated input.

`init` also creates an immutable inventory revision when checks change. Its reason
records additions, retirement, status changes, and explicit legacy migration.
Unchanged definitions retain eligible receipts. Changed definitions need new runs.
Use `--roadmap notes/roadmap.md` when that roadmap is selected evidence.

## Shapes and identity

All objects reject unknown/missing keys, wrong types, duplicate JSON keys, and
unsupported versions. Paths are canonical, literal repository-relative POSIX
paths without symlink traversal, `..`, backslashes, or absolute paths. Only cwd
and input roots can be `.`. The selected ledger is under `notes/epics/` and ends
in `.md`. JSON is UTF-8; canonical artifacts use sorted keys, no whitespace,
ASCII escapes, and one trailing newline. Hashes are lowercase SHA-256 hex.

The ledger contains exactly one JSON fence under `## Verification Contract`:

- `schema`: integer `1`.
- `ledger`: selected canonical path.
- `work_unit`: SHA-256 of that UTF-8 path, not its title.
- `inventories`: nonempty ordered list of `{path, sha256}` references, last current.
- `attempts`: ordered list of attempts, initially empty.

Each reference names `.deepdone/verification/<work_unit>/<category>/<sha256>.json`.
Categories are `inventories` and `receipts`. Its digest pins exact bytes. Every
historical reference is validated, including diagnostic and advisory receipts.
Artifacts are atomically installed without overwriting existing bytes. They are
never automatically staged or deleted, even when this namespace is not ignored.
Already staged artifacts remain intact and block commit as unowned work.

Inventory fields: `schema`, `work_unit`, `ledger`, positive consecutive `revision`,
nonempty `reason`, `roadmap` (null or `notes/roadmap.md`), and nonempty `checks`.
At least one check must be required. Check fields are exactly those in the example.
IDs match `[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}`, unique per revision. `required` is a
boolean; argv is a nonempty string array; env maps valid variable names to strings;
timeout is a finite number in `(0,3600]`. Inputs are `{path,role}`; roles are
`source` or `local-data`. Exclusions are `{path,reason}`. Acceptance is nonempty.
The definition digest hashes the whole canonical check, including its ID and
acceptance. Attempts, timestamps, output, and results do not enter this identity.

Attempt fields: positive consecutive `sequence`, unique 32-character lowercase
hex `id`, `check`, `definition` digest, `purpose`, `status`, `receipt`. Identity is
also bound to the enclosing ledger/work unit. Purpose is `diagnostic`, `feedback`,
or `readiness`; status is `pending` with null receipt, or `final` with a reference.

Ordinary receipt fields: `schema`, `ledger`, `work_unit`, `sequence`, `id`, `check`,
`definition`, `purpose`, `started`, `ended`, `argv`, `cwd`, `env`, `tool`, `before`,
`after`, `git_before`, `git_after`, `outcome`, `exit_code`, `output`, `error`.
Start/end are UTC ISO timestamps. Exit code is integer or null when unavailable.
Outcome is `completed`, `timeout`, `spawn-error`, `interrupted`, `capture-error`,
or `output-limit`. Nonzero completed executions retain their actual exit code.
Partial captures retain null unavailable fields and cannot pass.

- `tool`: resolved absolute executable path and SHA-256, or null before capture.
- `before`/`after`: `{sha256,entries}`, or null. Entries sorted by unique path,
  with `{path,kind,mode,sha256,role}`. Files use `100644` or `100755` (any executable
  bit); directories use empty mode/hash. Aggregate hash covers canonical entries.
- `git_before`/`git_after`: `{head,index_sha256}`, or null. Index hash is null if
  absent. Changed HEAD or real index blocks readiness; no reset or rollback.
- `output`: stdout/stderr objects with `{bytes,sha256,excerpt,truncated,complete}`,
  or null. Excerpts are base64 bytes, capped at 16 KiB each. Hash/count cover the
  consumed stream, not just its excerpt. Combined output above 8 MiB terminates
  execution; bounded pipe draining may consume additional bytes. Incomplete
  draining is marked `complete:false`. Invalid UTF-8 never requires decoding.
  If the host denies process-group signals, only the direct child is killed;
  descendants may outlive it. Draining remains bounded and the attempt cannot pass.
  Full output is not retained externally. Artifacts have a 16 MiB size limit.

Abandoned receipt fields: the same schema/work/attempt identity, `outcome` equal
to `abandoned`, and a nonempty `reason`. There are no invented execution fields.

## Execution and supported inputs

The wrapper holds a process-scoped nonblocking lock for the selected ledger,
registers pending state before launch, executes exact argv without an implicit
shell, and atomically finalizes only if ledger bytes and referenced inventory
remain unchanged. Competing writers fail; concurrent edits and completed orphan
artifacts are preserved. All participating writers must honor the lock. The
expected-byte check detects edits during execution; it is not an OS-level CAS
against an uncooperative editor racing the final check and rename.

The child receives only system default PATH plus explicit `env`, never the whole
ambient environment. Bare executable names resolve through that PATH relative to
the declared child cwd, including relative and empty PATH components. Relative
argv paths also use that cwd; wrapper invocation location is irrelevant. Launch
uses the resolved executable while preserving declared argv. Its bytes are pinned
and checked before/after and at gates. Failed prelaunch resolution/capture never launches
the command and finalizes valid nonpassing evidence where possible. Finalization,
history and CLI use the same execution-record validation; CLI success also requires
complete output and matching input/Git endpoints. CLI status describes this
execution, including diagnostic/feedback runs, not whole-inventory readiness.
The declared cwd must currently be a searchable directory under the supported
local path policy, even with absolute argv or cwd outside content input roots.
Check it before launch, after execution and at current required readiness gates.
Missing, nondirectory, symlinked or observed unusable cwd blocks. Post-execution
context loss preserves the child's raw exit but produces valid nonpassing evidence
and CLI failure. Repairing context permits a genuine later run; restoring the same
supported cwd does not create an inode-based stale condition. Historical receipt
integrity never requires obsolete or retired cwd paths to remain on disk. A
context-only cwd is not automatically Git source; when also declared source,
source materialization and current-context checks both apply.

Choose `context:"local-files"` only for checks whose relevant inputs
are captured repository files, declared environment values, and that executable.
Declare repository-local interpreters, libraries, wrapper files, and tool/config
inputs when relevant. Relevant external configuration/libraries, hidden Git
state, remote services, or unrepresentable toolchain context are unsupported:
stop and state the missing scope; do not declare `local-files` to waive it. This
is a declared applicability model, not automatic dependency inference or proof
against a command that lies about its inputs. Avoid secrets in argv/env/output;
those values are local evidence bytes.

Inputs are re-enumerated before execution, after execution, and at each gate.
They include tracked, untracked, and ignored files. Additions, deletions, renames,
content, kind, and executable-mode changes matter; mtimes and tracking status do
not. Relevant ignored source cannot be committed and blocks ownership validation.
Ignored untracked local data must explicitly use `local-data`; it remains local
context and is never promoted to committed source. Dirty relevant committable
inputs must belong to the reviewed changed set; unchanged base dependencies may
remain outside it. Read gates compare actual required source against Git trees,
including tree-side paths absent on disk, independently of status, index flags,
and `core.fileMode`. Capture checks the prospective tree before publication;
candidate/commit checks the captured tree; pre-Advance also checks committed HEAD.
Content, file kind, presence and executable mode must match. A mismatch blocks
without changing flags, config, index or user files. Filtered/materialized source
whose bytes differ from its Git blob is unsupported; supply an exact representable
source context before reviewing. Missing/unreadable paths, symlinks,
submodules/nested repos, and special files block. File watchers and network attestation are out of scope.

Ordinary source directories in the fingerprint must materialize from ancestors
of supported regular Git blobs, including committed descendants outside narrowly
selected leaves. Root `.` exists intrinsically; an empty tree object does not prove
materialization. An explicitly owned new descendant may establish a directory in
the prospective tree. Required empty directories otherwise block; helpers never
add markers or change declarations automatically. Local-data directories remain
local context. Stored fingerprints and receipts retain their existing structure.
Only the comparison projection omits a non-designated traversal parent whose
nonempty contents consist entirely of narrowly excluded evidence/generated paths
or such traversal parents. Explicit input roots and unexcluded empty children
never receive that exemption, including under `notes/` or `.deepdone/`.

Exclude only `.git`, selected ledger/roadmap, canonical task records, the verification
namespace, exact `.deepdone/commit-candidate.md`, and `.deepdone/reviews/*.json`
evidence files. For a selected task, also exclude canonical `notes/epics/**/*.md`
records and exactly `notes/roadmap.md` from source projection and ownership;
they remain unrelated state, not additional task evidence. Epic projection is unchanged.
Evidence-container directory entries are omitted while ordinary contained files
are still scanned. Ordinary `notes/`, `.deepdone/`, and ignored content remain
inputs when under a declared root. Do not put relevant source under evidence
paths. Explicit generated exclusions are definition-bound and need review.

Equal fingerprints establish matching observed endpoints. A file changed and
reverted entirely between observations is not detected. Readiness does not claim
stronger execution attestation. Files must remain stable during consuming gates;
the helpers do not lock the entire worktree against external writers.

## Selection, recovery, and migration

Only the latest readiness attempt for each current required definition can pass:
normal completion, exit zero, complete output, unchanged before/after inputs and
Git context, current matching inputs and executable, and intact references.
A later failure, pending, abandoned, or stale readiness attempt cannot select an
older convenient pass. A new matching successful run supersedes valid failures
without deleting them. Diagnostic/feedback runs cannot satisfy readiness or be
promoted by editing purpose. Advisory failures alone do not block, but malformed
artifacts and any unresolved pending attempt remain integrity blockers.

A killed runner can leave pending state. Inspect it, then deliberately record:

```sh
python3 "$SCRIPT" abandon --ledger notes/epics/demo.md --attempt-id <id> --reason 'Runner interrupted; output incomplete'
python3 "$SCRIPT" run --ledger notes/epics/demo.md --check-id unit --purpose readiness
```

The process lock releases on exit; do not delete history to recover. Abandonment
never restores an older pass. STOP is checked before new wrapper work.

Legacy `Verification Log` text remains unchanged, including failures or malformed
notes. New capture/candidate/commit requires deliberate `init`, actual readiness
runs, and a new review. Legacy strings cannot mint receipts. After migration they
are historical display, not another readiness parser. Missing/deleted contract
is a blocker, never a fallback to old `pass`. Damaged contracts must be restored
before revision. Clean already committed historical Advance retains bounded
compatibility after applicable manifest/evidence validation and is not labelled
receipt-verified. Before weaker compatibility, structured earlier Review records
and identifiable retained manifests for this ledger must establish eligibility.
Retained stronger, missing, unreadable or contradictory applicable provenance
blocks a later short-form/missing/schema-1 fallback. Unrelated ledgers do not
establish this ledger's history. A valid current schema-v2 review can supersede
older captures without revalidating their obsolete ledger hashes. New-format
evidence cannot use historical compatibility.

Capture, candidate, actual commit preflight, and pre-Advance follow the full chain:
schema-v2 manifest hashes ledger; ledger pins inventories and receipts; receipts
bind definitions, execution, and current inputs. Sidecar edits fail pinned hashes;
updated ledger refs require new review. Run normal Advance validation before
intentional ledger/roadmap transition; cleanup does not repeat freshness checks
after that transition. Commit authorization and phase/mode budgets are unchanged.

## Compact task records

Use `--task .deepdone/tasks/<id>.md` instead of `--ledger` for every action. See [task contract](task-contract.md) for strict metadata and acceptance binding. Inventory/receipt schema 1 and review manifest schema 2 are unchanged; `ledger` and `ledger_path` mean the selected durable work record. Current task acceptance binds to proposed inventories at revision and current inventories at readiness, while old receipt history retains its original definitions. Tasks cannot associate a roadmap or use legacy receipt-free compatibility.
