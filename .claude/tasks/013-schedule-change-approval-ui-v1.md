# Task 013 — Schedule change approval UI V1

## Goal
Complete the smallest useful next slice after employee `/grafik` requests: let the existing Nazoratchi/Founder HR flow view pending schedule-change requests and approve or reject one safely.

## Constraints
- NATIVE WINDOWS EXECUTION = 0. Do not use Windows, PowerShell, or local Windows paths/runtime.
- Work only on `feature/hr-conversational-interview`; never touch `main` or production.
- Read only the relevant existing attendance/schedule-change service, HR/Nazoratchi handlers, and targeted tests. No repo-wide audit.
- Reuse existing `services/attendance` request/approval functions and current permission model. Do not duplicate business logic or add dependencies.
- Minimal diff. Do not edit files under `.claude/tasks/` in the result commit.

## Required behavior
1. Add one simple entry in the existing Nazoratchi/Founder HR UI for pending schedule-change requests.
2. Show pending requests in plain Uzbek with employee identity, requested date, request type, and requested time when applicable.
3. Provide `✅ Tasdiqlash` and `❌ Rad etish` actions for a selected pending request.
4. Approval must go through the existing canonical approval/service path so the schedule updates only through that logic; rejection must mark the request rejected without changing the schedule.
5. Re-check request status/authorization at action time so stale/double clicks cannot apply twice.
6. Give a short user-facing success/error message and return to the pending list/menu.

## Acceptance
- Add/update only focused tests for: pending list visibility, approve once, reject without schedule mutation, and stale/double action safety.
- Run the narrowest relevant tests on Linux/CI first. Run broader tests only if the change itself shows a regression risk.
- If targeted tests pass, commit and push the implementation to the same feature branch.
