# App Shell

## Summary

Create minimal offline notes app shell for the active roadmap epic.

## Constraints

- Keep sync behavior out of this epic.
- Use existing app framework and command wrappers.

## Milestones

- [ ] create shell route
  - touched areas: app routing and top-level page
  - acceptance: root route renders shell and note list placeholder
  - risks: route collision with existing pages
  - research: none
  - depends on: none

- [ ] add smoke verification
  - touched areas: test or smoke command nearest app entry
  - acceptance: one local command proves shell loads
  - risks: smoke test may be too shallow
  - research: none
  - depends on: create shell route

## Decisions

- none yet

## Verification Log

- command: `just test app-shell`
  result: blocked
  notes: command discovery not run yet

## Open Loops

- none

## Next Action

Discover the nearest app verification command, then implement shell route.

## Status

active
