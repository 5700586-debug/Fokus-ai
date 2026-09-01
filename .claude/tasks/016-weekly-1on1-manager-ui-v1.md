# Task 016 — Weekly 1:1 manager UI V1

Goal: expose the existing `services/one_on_one.py` core through a minimal Telegram flow for Founder/Nazoratchi to record one weekly 1:1 with an approved employee.

Hard rules:
- NATIVE WINDOWS EXECUTION = 0. No Windows/PowerShell/local Windows paths or tests. Linux/GitHub Actions only.
- Stay on `feature/hr-conversational-interview`; never touch `main` or production.
- Reuse existing employee-card/menu, branch-access and FSM patterns. No parallel employee/permission model, no new dependency.
- Use only existing `services.one_on_one` APIs for create/read/follow-up state; do not bypass them with direct DB writes.
- Do not add scheduler, automatic reminders, employee notification, bonus/minus, AI/psychological scoring, or analytics in this task.

Implement one simple manager flow:
1. From the existing employee management/card area, add one clear action for weekly 1:1.
2. Re-check actor permission + branch access at action time; employee must still be `approved`.
3. If this week already has a record, show it read-only instead of creating a duplicate.
4. Otherwise collect exactly one of the 5 existing outcomes, an optional short summary, and optional follow-up text; save via `create_one_on_one`.
5. If an older open follow-up exists, show it before the new conversation and allow the manager to mark it resolved via `resolve_followup`.
6. Clear FSM on success/cancel/error using the repository's existing pattern.

Acceptance:
- Founder/Nazoratchi can record one weekly 1:1 for an accessible approved employee.
- Duplicate same-week write is impossible and displayed cleanly.
- Cross-branch/unauthorized/offboarded access is denied.
- Existing open follow-up can be viewed and resolved; no DELETE/history loss.
- Add focused tests for this UI flow only. Run the narrowest relevant Linux tests first; expand only if a real failure/risk requires it.
- Minimal diff. Update `docs/PROJECT_STATE.md` only after PASS.
- Do not modify any `.claude/tasks/` file in the result commit.