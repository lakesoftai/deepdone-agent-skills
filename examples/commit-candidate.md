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

## Reviewed Files

- `M` `src/auth/middleware.py`
- `A` `tests/test_auth_errors.py`
- `M` `notes/epics/2026-05-18-auth-error-cleanup.md`

## Excluded Unreviewed Files

- `??` `scratch-notes.txt`

## Stale Reviewed Files

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
  paths:
    - src/auth/middleware.py
    - tests/test_auth_errors.py
    - notes/epics/2026-05-18-auth-error-cleanup.md
  notes: no blocking findings

## Open Loops

- none

## Commit Gate

- pass
