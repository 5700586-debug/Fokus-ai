FOKUS AI — employee schedule-change request UI V1.

Goal: expose the existing `create_schedule_change_request` core to employees in Telegram with the smallest safe UI. Do NOT build supervisor approval UI yet.

Rules:
- NATIVE WINDOWS EXECUTION = 0. Run only on Linux/GitHub Actions.
- Stay on `feature/hr-conversational-interview`; never touch `main` or production.
- Read only the relevant employee dashboard/menu handlers plus `services/attendance.py` and current schedule-change tests. No repo-wide audit.
- Reuse the existing schedule-change core; do not create a second schedule/request system or new dependency.
- Minimal diff; preserve existing menu/UX conventions.

Implement:
1. Add one clear employee action such as `📅 Grafikni o‘zgartirish` in the existing employee-facing menu/dashboard.
2. Simple guided flow for ONE date: choose `Dam olish` OR `Ish vaqti`; for work collect date + start + end and existing mode only if the current architecture requires it; optional short reason.
3. Resolve the current Telegram user to the canonical approved employee profile. Reject missing/offboarded/non-approved profiles cleanly.
4. Submit only through `services.attendance.create_schedule_change_request`; do not modify schedule directly.
5. On success show a short human message: request accepted and waiting for supervisor approval. On validation/error show one simple actionable message, no traceback/internal terms.
6. Prevent accidental duplicate FSM state leakage/cross-user data; clear flow state on success/cancel/error according to existing bot patterns.

Acceptance:
- Employee can create valid `off` and `work` requests from Telegram.
- Invalid time/date/profile does not create a request.
- Existing schedule is unchanged until approval.
- Existing core tests still pass.
- Add only focused UI tests for the new flow; run the narrowest relevant Linux tests first. Broaden only if a real regression requires it.
- PASS => commit/push to this feature branch.
- Do not modify any `.claude/tasks/` file in the result commit.
