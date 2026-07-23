# DeepDone Commit Candidate

## Message

```text
auth: normalize auth error responses

DeepDone:
- Epic: Auth Error Cleanup
- Milestone: normalize auth errors
- Verification:
  - command: `pytest tests/test_auth_errors.py`
    result: pass
    notes: invalid credentials and expired session cases pass
- Review:
  - result: pass
```

## Reviewed Git Snapshot

- ref: `refs/deepdone/reviews/20260518T120000Z-a1b2c3d4`
- tree: `89abcdef0123456789abcdef0123456789abcdef`
- changed paths: 2
- include: `src/auth/`
- include: `tests/`

## Reviewed Status Sample

- `M` `src/auth/middleware.py`
- `A` `tests/test_auth_errors.py`

## Excluded Unreviewed Files

- `??` `scratch-notes.txt`

## Stale Reviewed Path Sample

- none

## Staged Unowned Files

- none

## Excluded Local Files

- none

## Verification

- command: `pytest tests/test_auth_errors.py`
  result: pass
  notes: invalid credentials and expired session cases pass

## Review

- reviewed-at: 2026-05-18T12:00:00Z
  result: pass
  review-id: 20260518T120000Z-a1b2c3d4
  base-head: 0123456789abcdef0123456789abcdef01234567
  manifest: .deepdone/reviews/20260518T120000Z-a1b2c3d4.json
  scope:
    include:
      - src/auth/
      - tests/
    exclude:
  evidence:
    ledger: notes/epics/2026-05-18-auth-error-cleanup.md
  notes: no blocking findings

## Open Loops

- none

## Commit Gate

- pass
