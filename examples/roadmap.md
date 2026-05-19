# Offline Notes Initiative

## Summary

Build recoverable offline note browsing in two epics: app shell first, sync behavior second.

## Constraints

- Keep first epic limited to local shell, routing, and smoke verification.
- Do not implement network sync until shell verification passes.

## Cross-Cutting Decisions

- 2026-05-18: local state owner
  - scope: app-shell, offline-sync
  - chosen: keep note cache state in existing app store
  - reason: later sync epic must reuse shell state contracts
  - source ledger: notes/epics/2026-05-18-app-shell.md

## Epic Queue

- [-] app-shell
  - goal: create app shell, routes, and local note list placeholder
  - exit criteria: app boots, routes work, smoke check passes
  - depends on: none
  - ledger: notes/epics/2026-05-18-app-shell.md

- [ ] offline-sync
  - goal: cache notes locally and reconcile when network returns
  - exit criteria: offline read works, queued edits sync, conflict path tested
  - depends on: app-shell
  - ledger: not-created

## Active Epic

- name: app-shell
- ledger: notes/epics/2026-05-18-app-shell.md
- state: active

## Status

active
