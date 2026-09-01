# Task: schedule-change decision notification V1

Work only on `feature/hr-conversational-interview`. NATIVE WINDOWS EXECUTION = 0. Use Linux/GitHub Actions only. Do not touch `main` or production.

Goal: close the existing `/grafik` request loop by notifying the employee in Telegram after a Nazoratchi/Founder successfully approves or rejects the request.

Scope:
- Read only the relevant schedule-request flow in `nazoratchi_bot.py`, `services/attendance.py`, employee/repository lookup code, and existing notification patterns/tests.
- Reuse existing employee Telegram identity and message-sending patterns; no new dependency/schema unless strictly necessary.
- Send notification only after the canonical decision succeeds. Include date + approved/rejected status; for approved work/off requests, include the resulting requested schedule summary already available from the request.
- If Telegram delivery fails, keep the already-committed decision; log/handle the send failure without rolling back or crashing the decision flow.
- Stale/double-clicked decisions must not send duplicate notifications.
- Keep permissions, atomic pending->approved/rejected behavior, and schedule update path unchanged.

Acceptance:
1. Approved request -> employee gets one clear Telegram notification.
2. Rejected request -> employee gets one clear Telegram notification.
3. Failed message delivery does not undo the DB decision or schedule result.
4. Repeated/stale callback does not send another employee notification.
5. Add/update only focused tests for this behavior; run the narrowest relevant pytest set on Linux. Expand only if a real dependency requires it.
6. Minimal diff. If tests pass, commit and push to the same feature branch. Do not modify `.claude/tasks/` in the result commit.
