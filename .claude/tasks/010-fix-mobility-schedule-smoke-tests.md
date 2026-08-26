# Task: repair mobility/schedule UI smoke tests

Work only on `feature/hr-conversational-interview`. NATIVE WINDOWS EXECUTION = 0; run tests only on Linux (`ubuntu-latest`). Do not touch `main` or production.

Known issue from `docs/PROJECT_STATE.md`: `tests/test_mobility_management_ui.py` and `tests/test_schedule_management_ui.py` are in `smoke-tests.yml`, but async tests lack the project’s AnyIO marker/backend setup. Adding that exposes 8 stale assertions, mainly because callback answers now occupy `sent[0]`.

Goal: make these two test files accurately reflect the current intended bot behavior without changing production behavior unless a real defect is proven.

Do:
1. Read only these two tests plus the directly related handlers/helpers and existing nearby test patterns.
2. Add the minimal project-consistent AnyIO setup.
3. Fix only stale/brittle assertions so they assert semantic outputs, not incidental send-order indexes, where appropriate.
4. Prefer test-only changes. If you find a genuine app bug, make the smallest justified fix and explain it in the commit.
5. Run only:
   `pytest tests/test_mobility_management_ui.py tests/test_schedule_management_ui.py -q`
   on Linux.
6. Acceptance: both files PASS with no xfail/skip/continue-on-error added and no weakened assertions that would hide a real regression.
7. Commit and push to this feature branch. Do not modify any `.claude/tasks/` file in the result commit.

Keep the diff small; no repo-wide audit, dependency upgrade, refactor, full suite, Render deploy, or production work.