# DeepDone Orchestrate State Machine

This reference supports the smart supervisor skill. It is a map, not a cage.

## States

```text
no_state
needs_intake
needs_resume
needs_advance_roadmap
needs_tech_decision
ready_to_implement
needs_verification
needs_review
needs_review_fix
ready_for_commit_candidate
ready_to_commit
blocked_needs_user
complete
```

## Normal Flow

```text
requirements
  -> needs_intake
  -> needs_advance_roadmap
  -> ready_to_implement
  -> needs_verification
  -> ready_to_implement | needs_review
  -> needs_review_fix | ready_for_commit_candidate
  -> ready_to_commit
  -> needs_advance_roadmap
  -> complete
```

## Resume Flow

```text
unknown or interrupted state
  -> inspect git, roadmap, ledger, logs
  -> needs_resume
  -> one of the normal states
```

## Decision Flow

```text
milestone has unresolved research
  -> needs_tech_decision
  -> ready_to_implement or blocked_needs_user
```

## Review Flow

```text
needs_review
  -> no findings -> ready_for_commit_candidate
  -> local mechanical findings -> needs_review_fix
  -> risky findings -> blocked_needs_user
```

## Stop Rules

Stop immediately if the next transition would require guessing product intent, architecture preference, risk tolerance, or approval not already authorized by selected mode.
