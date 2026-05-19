# DeepDone PR Draft

## Title

auth: normalize auth error responses

## Body

```md
## Summary

- Normalize authentication failure responses.
- Add focused regression coverage for invalid credentials and expired sessions.

## DeepDone

- Epic: Auth Error Cleanup
- Ledger: notes/epics/2026-05-18-auth-error-cleanup.md
- Milestone: normalize auth errors
- Review: pass

## Verification

- command: `pytest tests/test_auth_errors.py`
  result: pass
  notes: invalid credentials and expired session cases pass

## Open Loops

- none
```

## Next Action

Create PR only after branch publish and target branch are explicitly confirmed.
