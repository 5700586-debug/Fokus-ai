READ-ONLY ARCHITECTURE AUDIT. Do not edit application code, commit generated changes, open PR, or deploy.

WINDOWS=0. Linux only. Token econom. No subagents.
PR #22 and cash OCR files are out of scope.

Read only:
- main.py
- roles.py
- services/e2e_test_access.py
- tests/test_role_test_sandbox.py
- tests/test_e2e_tester_role.py
- tests/test_e2e_test_isolation.py
- repository functions directly called by those files

Known current design:
- Founder "Rol testi" exists only in ENVIRONMENT=test and blocks real writes.
- Static E2E tester reuses real cash handlers with is_test + test_run_id.
- Do not propose a third parallel test system.

Goal: map the minimal safe way to combine the two into one Founder-only role-switching sandbox inside the real bot.

Determine:
1. Existing sandbox pieces to reuse.
2. Existing E2E pieces to reuse.
3. Safe FSM behavior during role switching.
4. DB and notification isolation from real KPI, bonus, reports, and employees.
5. Exact Touch ONLY files for the first smallest implementation stage.

Output exactly 7 lines:
1. BASE: <HEAD SHA>
2. SANDBOX REUSE: ...
3. E2E REUSE: ...
4. FSM: ...
5. ISOLATION: ...
6. TOUCH ONLY: ...
7. RISK: ...
