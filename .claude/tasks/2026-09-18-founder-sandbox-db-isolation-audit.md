I/S+ SENIOR ARCHITECTURE AUDIT. Token econom. WINDOWS=0. No subagents.

READ-ONLY ONLY. Do not edit application code, commit generated changes, open PR, merge, or deploy.

Goal:
The Founder sandbox must run the EXACT real cashier flow (open shift, upload both ledger photos, AI/manual extraction, close shift) while every write and notification is absolutely isolated from production data. Long TEST banners must appear only once on entry; later messages use only a short 🧪 marker.

Critical finding:
is_test/test_run_id currently exists only on cash_shifts and shift_deficiency_items. The real close flow also writes expenses, daily reports, complaints, deficiencies, photo refs, cleanup state, and sends notifications. Simply allowing handlers through is forbidden because it can contaminate real data.

Inspect ONLY:
- db.py
- db_postgres.py
- storage.py
- main.py
- cash_shift_bot.py
- services/e2e_test_access.py
- services/cash_shift.py
- services/cash_expense.py
- services/shift_daily_report.py
- services/shift_deficiency.py
- services/notifications.py
- repositories directly called by those services
- tests/test_role_test_sandbox.py
- tests/test_cash_shift_bot_flows.py
- tests/test_e2e_test_isolation.py

Compare these two safe designs:
A) per-update ContextVar DB routing to TEST_DATABASE_URL while reusing exact handlers;
B) extending is_test/test_run_id to every table touched by the cash flow.

Rules:
- One bot, one codebase, same handlers.
- No third parallel flow.
- No real employee notification in sandbox; redirect back to Founder with 🧪.
- Role switching must keep saved sandbox DB data but clear transient FSM safely.
- Identify how Founder profile/branch/permissions will resolve inside isolated storage.
- Identify required Render env dependency without changing it.
- Recommend the smallest safe design; do not code.

Output exactly 8 lines:
1. BASE
2. WRITES TO ISOLATE
3. DESIGN A
4. DESIGN B
5. RECOMMENDATION
6. TOUCH ONLY FOR FOUNDATION
7. TEST PLAN
8. BLOCKER
