# Auth Error Cleanup

## Summary

Make authentication failures return stable JSON errors without changing successful login behavior.

## Constraints

- No schema changes.
- Preserve current token issuance and session expiry behavior.

## Milestones

- [x] normalize auth errors
  - touched areas: auth middleware and error response tests
  - acceptance: invalid credentials and expired sessions return documented JSON shape
  - risks: leaking internal auth reason
  - research: none
  - depends on: none

## Decisions

- review-result: pass

## Verification Log

- command: `pytest tests/test_auth_errors.py`
  result: pass
  notes: invalid credentials and expired session cases pass

## Open Loops

- none

## Next Action

No action. Epic archived after merge.

## Status

archived
- archived: 2026-05-18
- merge/ref: https://example.com/org/repo/pull/42
- post-merge verification: pass
