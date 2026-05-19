# Review Finding Triage

## Auto-fix

Auto-fix when the finding is local, clear, low risk, and directly covered by a targeted check.

Examples:

- missed edge case in changed function
- wrong condition
- missing local test
- type error caused by current change
- obvious exception path

## Ask user

Ask user when the finding changes what the product should do or how the architecture should evolve.

Examples:

- auth/permission behavior
- persistence or migration behavior
- public API contract
- larger refactor
- performance versus correctness tradeoff
- UX or product semantics

## Reject or defer

Reject only when evidence shows the finding is invalid. Record why.

Defer when it is valid but outside the active milestone.
