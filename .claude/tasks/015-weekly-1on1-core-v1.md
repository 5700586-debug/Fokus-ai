# Task: Weekly employee 1:1 core V1

Implement only the backend/core foundation for weekly manager–employee 1:1 conversations. No Telegram UI yet.

## Goal
Create one canonical service/storage path that can record a short weekly 1:1 for an approved employee and preserve unresolved follow-ups for the next conversation.

## Scope
- Reuse existing employee/branch/permission patterns; do not create a parallel employee model.
- Add the smallest schema/service needed to store: employee_id, manager/actor id, branch, week/date, status outcome, optional short summary, created/updated timestamps.
- Allowed outcome values only: `ok`, `difficulty`, `suggestion`, `serious_issue`, `other`.
- Support an optional follow-up item with text + open/resolved state, so an unresolved item can be retrieved for the employee’s next 1:1.
- Prevent duplicate active/completed 1:1 records for the same employee and week through a clear canonical rule.
- Reject unknown/offboarded/unapproved employees using existing profile/status logic.
- Do not add psychological diagnosis, scoring, sentiment analysis, bonus/minus logic, notifications, scheduler, or Telegram UI.
- No new dependency unless absolutely necessary.

## Tests
Add one focused Linux test file covering: create valid 1:1, invalid outcome, offboarded/unapproved rejection, duplicate same-week protection, open follow-up retrieval, resolving follow-up. Run only this targeted test first; expand only if a real dependency/regression requires it.

## Hard constraints
- NATIVE WINDOWS EXECUTION = 0. Never use Windows, PowerShell, local Windows paths/runtime/tests. Execution/tests only on GitHub Actions `ubuntu-latest`.
- Minimal diff; preserve existing architecture and data/history.
- Do not touch `main`, production, secrets, billing, deploy config, or unrelated modules.
- Do not edit `.claude/tasks/` in the result commit.
- If targeted Linux tests pass, commit and push to `feature/hr-conversational-interview`.

## Acceptance
A caller can create one weekly 1:1 record for an approved employee, store one of the five explicit outcomes, carry an unresolved follow-up into the next lookup, resolve it later, and duplicate same-week creation is safely blocked; targeted Linux tests pass.