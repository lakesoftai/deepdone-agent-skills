# Auth Error Cleanup

## Summary

Make authentication failures return stable JSON errors without changing successful login behavior.

## Constraints

- No schema changes.
- Preserve current token issuance and session expiry behavior.

## Milestones

- [ ] normalize auth errors
  - touched areas: auth middleware and error response tests
  - acceptance: invalid credentials and expired sessions return documented JSON shape
  - risks: leaking internal auth reason
  - research: none
  - depends on: none

- [ ] verify regression surface
  - touched areas: auth tests and smoke check
  - acceptance: existing login success path still passes
  - risks: weak test isolation
  - research: none
  - depends on: normalize auth errors

## Decisions

- none yet

<!-- Summary-only example. Before new Review capture, initialize a real Verification
Contract with scripts/verification.py init, execute required readiness checks,
and keep the wrapper-generated references. Do not copy invented receipts. -->

## Verification Log

- command: `pytest tests/test_auth_errors.py`
  result: blocked
  notes: test file not written yet

## Review

- reviewed-at: not-run
  result: pending
  notes: implementation not reviewed yet

## Open Loops

- none

## Next Action

Implement normalized auth error response and focused tests.

## Status

active
