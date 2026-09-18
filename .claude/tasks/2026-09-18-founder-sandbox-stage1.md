I/S+ IMPLEMENTATION — STAGE 1 ONLY. Token econom. WINDOWS=0. No subagents.

Repository: 5700586-debug/Fokus-ai
Branch: feature/hr-conversational-interview
Expected parent before this task commit: 56d43e4645f9e54b6c4dc8ace0400bfe3572212b.
First verify: git rev-parse HEAD^ must equal that SHA; otherwise STOP.

Goal:
Expose the EXISTING "🧪 Rol testi" preview inside the production bot to FOUNDER_ID only, while keeping it strictly preview-only with zero writes and safe FSM entry.

Touch ONLY:
- main.py
- tests/test_role_test_sandbox.py

Required changes:
1. Add one small helper such as _sandbox_enabled(user_id) that returns true only for user_id == FOUNDER_ID. Do not depend on ENVIRONMENT for sandbox visibility.
2. Use that helper in both existing ENVIRONMENT=test gates controlling the Founder role-test button/entry. Do not widen access to any other user.
3. Before entering role picking, call await state.clear(), then set preview_picking=True. This must remove any unfinished real-flow FSM state.
4. Keep _SandboxPreviewMiddleware outermost and keep preview actions blocked from real handlers. Do not enable writes, callbacks, notifications, E2E cash writes, or test_run_id in this stage.
5. Keep all existing narrow escape rules unchanged.
6. Update/add targeted tests proving:
   - Founder sees the role-test button in production and test environments.
   - non-Founder never sees/opens it.
   - entering sandbox clears pre-existing FSM state.
   - preview mutating action still writes nothing.
   - exit and /start recovery tests remain green.

Forbidden:
- No edits to roles.py, services/e2e_test_access.py, repositories, schema, workflows, config, OCR files, or task files.
- No new parallel sandbox.
- No main, PR, merge, Render, or production deploy.
- No full test suite.

Run only:
pytest tests/test_role_test_sandbox.py -q

If another file is required, STOP without editing it.

PASS only: commit and push to the same branch.
Output exactly 6 lines:
1. BASE
2. FILES
3. CHANGE
4. TEST
5. COMMIT
6. MAIN/PRODUCTION
