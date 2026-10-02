from repositories import cash_shifts as repo


def test_open_shift_creates_row():
    shift = repo.open_shift(1, "Chilonzor filiali", "2026-01-01", opening_balance=0, tolerance=20000)

    assert shift["employee_id"] == 1
    assert shift["shift_date"] == "2026-01-01"
    assert shift["status"] == "open"
    assert shift["opening_balance"] == 0


def test_open_shift_is_idempotent_for_same_day():
    first = repo.open_shift(1, "Chilonzor filiali", "2026-01-01", opening_balance=0, tolerance=20000)
    second = repo.open_shift(1, "Chilonzor filiali", "2026-01-01", opening_balance=500000, tolerance=20000)

    assert first["id"] == second["id"]
    assert second["opening_balance"] == 0  # yangisi bilan almashtirilmadi


def test_get_last_closed_shift_ignores_open_shifts():
    repo.open_shift(1, "Filial-1", "2026-01-01", opening_balance=0, tolerance=20000)
    assert repo.get_last_closed_shift("Filial-1") is None

    shift = repo.get_open_shift(1, "2026-01-01")
    repo.update_shift_result(
        shift["id"],
        cash_sales=100,
        card_sales=0,
        other_payments=0,
        total_sales=100,
        cash_expenses=0,
        expected_cash_balance=100,
        actual_cash_balance=100,
        difference=0,
        status="clean_closed",
        close=True,
    )

    last_closed = repo.get_last_closed_shift("Filial-1")
    assert last_closed["id"] == shift["id"]
    assert last_closed["actual_cash_balance"] == 100
    assert last_closed["closed_at"] is not None


def test_set_shift_status_if_only_updates_when_status_matches():
    """Atomic guard: ikkita "parallel" chaqiruv (masalan ikki marta
    bosilgan tugma) bir smenani ikki marta o'zgartirmasligi kerak —
    birinchisi ``True`` (yangiladi), ikkinchisi ``False`` (joriy status
    endi kutilganidan farq qiladi, hech narsa o'zgarmadi) qaytarishi
    kerak.
    """
    shift = repo.open_shift(1, "Filial-1", "2026-01-01", opening_balance=0, tolerance=20000)
    repo.set_shift_status(shift["id"], "needs_supervisor_approval", close=False)

    first = repo.set_shift_status_if(
        shift["id"], "needs_supervisor_approval", "approved_by_supervisor", close=True
    )
    second = repo.set_shift_status_if(
        shift["id"], "needs_supervisor_approval", "rejected_by_supervisor", close=True
    )

    assert first is True
    assert second is False

    updated = repo.get_shift(shift["id"])
    assert updated["status"] == "approved_by_supervisor"  # ikkinchi urinish o'zgartirmadi


def test_increment_retry_count():
    shift = repo.open_shift(1, None, "2026-01-01", opening_balance=0, tolerance=20000)

    assert repo.increment_retry_count(shift["id"]) == 1
    assert repo.increment_retry_count(shift["id"]) == 2


def test_difference_review_recorded_in_order():
    shift = repo.open_shift(1, None, "2026-01-01", opening_balance=0, tolerance=20000)

    repo.record_difference_review(shift["id"], 1, actual_cash_balance=900, difference=-100, status_after="recheck_required")
    repo.record_difference_review(shift["id"], 2, actual_cash_balance=950, difference=-50, status_after="recheck_required")

    reviews = repo.get_difference_reviews(shift["id"])
    assert [r["attempt_number"] for r in reviews] == [1, 2]


def test_shift_approval_recorded():
    shift = repo.open_shift(1, None, "2026-01-01", opening_balance=0, tolerance=20000)

    repo.record_shift_approval(shift["id"], reviewed_by=999, decision="approved", comment="OK")

    # Faqat yozilishi kerak, o'qish uchun alohida getter yo'q hozircha —
    # xatosiz yozilgani yetarli (FK buzilmasligi tekshiriladi).


def test_add_and_list_expenses_for_shift():
    shift = repo.open_shift(1, "Filial-1", "2026-01-01", opening_balance=0, tolerance=20000)

    repo.add_expense(shift["id"], 1, "Filial-1", "taxi", 65000, "Yetkazib berish", "2026-01-01")
    repo.add_expense(shift["id"], 1, "Filial-1", "taxi", 70000, None, "2026-01-01")

    expenses = repo.get_expenses_for_shift(shift["id"])
    assert len(expenses) == 2
    assert {e["amount"] for e in expenses} == {65000, 70000}


def test_get_expense_history_excludes_today_and_orders_desc():
    shift1 = repo.open_shift(1, None, "2026-01-01", opening_balance=0, tolerance=20000)
    shift2 = repo.open_shift(1, None, "2026-01-02", opening_balance=0, tolerance=20000)

    repo.add_expense(shift1["id"], 1, None, "taxi", 60000, None, "2026-01-01")
    repo.add_expense(shift2["id"], 1, None, "taxi", 999999, None, "2026-01-02")

    history = repo.get_expense_history(1, "taxi", before_date="2026-01-02")
    assert len(history) == 1
    assert history[0]["amount"] == 60000


def test_ledger_expense_items_replace_without_duplicates_and_total_uses_amount_only(temp_db):
    from repositories import cash_shifts as repo
    from services import cash_expense

    shift = repo.open_shift(1, "Filial-1", "2026-10-01", 0, 20000)
    items = [
        {"raw_name": "abinon", "normalized_name": "Obinon", "amount": 198000},
        {"raw_name": "Vilka", "normalized_name": "Vilka", "amount": 220000},
    ]
    assert cash_expense.save_ledger_items(shift["id"], items) == 2
    assert cash_expense.save_ledger_items(shift["id"], items) == 2  # qayta urinish dublikat yaratmaydi

    saved = cash_expense.get_ledger_items(shift["id"])
    assert [(r["line_no"], r["raw_name"], r["normalized_name"], r["amount"]) for r in saved] == [
        (1, "abinon", "Obinon", 198000), (2, "Vilka", "Vilka", 220000),
    ]
    assert cash_expense.total_ledger_expenses(shift["id"]) == 418000

    # Nom xato o'qilsa ham jami o'zgarmaydi (faqat amount hisoblanadi).
    cash_expense.save_ledger_items(shift["id"], [
        {"raw_name": "???", "normalized_name": None, "amount": 198000},
        {"raw_name": "Vilkaa", "normalized_name": "", "amount": 220000},
    ])
    assert cash_expense.total_ledger_expenses(shift["id"]) == 418000
    assert [r["normalized_name"] for r in cash_expense.get_ledger_items(shift["id"])] == ["???", "Vilkaa"]


def test_ledger_summary_status_saved_replaced_and_cleared_with_items(temp_db):
    import pytest

    from repositories import cash_shifts as repo
    from services import cash_expense

    shift = repo.open_shift(1, "Filial-1", "2026-10-01", 0, 20000)
    items = [
        {"raw_name": "abinon", "normalized_name": "Obinon", "amount": 198000},
        {"raw_name": "Vilka", "normalized_name": "Vilka", "amount": 220000},
    ]
    cash_expense.save_ledger_items(
        shift["id"], items, total_status=cash_expense.LEDGER_STATUS_ACCEPTED_WRITTEN_TOTAL,
        written_total=500000, accepted_total=500000,
    )
    summary = cash_expense.get_ledger_summary(shift["id"])
    assert (summary["total_status"], summary["items_sum"], summary["written_total"], summary["accepted_total"]) == (
        "cashier_accepted_written_total", 418000, 500000, 500000,
    )

    cash_expense.save_ledger_items(shift["id"], items)  # qayta tasdiq — almashtiriladi, dublikat yo'q
    summary = cash_expense.get_ledger_summary(shift["id"])
    assert summary["total_status"] == "matched" and summary["accepted_total"] == 418000
    assert len(cash_expense.get_ledger_items(shift["id"])) == 2

    cash_expense.save_ledger_items(shift["id"], [])  # bo'sh tasdiqlangan natija — qatorlar va holat tozalanadi
    assert cash_expense.get_ledger_items(shift["id"]) == [] and cash_expense.get_ledger_summary(shift["id"]) is None

    with pytest.raises(ValueError):
        cash_expense.save_ledger_items(shift["id"], items, total_status="mismatch_unresolved")
