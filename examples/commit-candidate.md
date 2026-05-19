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
  - review-result: pass
```

## Files

- `M` `src/auth/middleware.py`
- `A` `tests/test_auth_errors.py`

## Excluded Local Files

- none

## Verification

- command: `pytest tests/test_auth_errors.py`
  result: pass
  notes: invalid credentials and expired session cases pass

## Review

- review-result: pass
- no blocking findings

## Open Loops

- none

## Commit Gate

- pass
