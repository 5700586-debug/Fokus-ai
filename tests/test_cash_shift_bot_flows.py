import pytest

from config import FOUNDER_ID
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_kassir(user_id: int, branch: str = "Filial-1") -> None:
    from roles import set_role
    import employees

    set_role(user_id, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Kassirov", "ism": "Ali", "otasining_ismi": "Vali",
            "branch": branch, "role_key": "kassir", "contacts": [],
        },
    )


async def _open_shift(main, bot, user_id: int, opening_balance: str = "0") -> None:
    await send(main.dp, bot, user_id, text="/openshift")
    await send(main.dp, bot, user_id, text=opening_balance)


async def _close_shift_happy_path(
    main, bot, user_id: int, cash_sales="100000", card_sales="0", other="0", actual="100000"
):
    await send(main.dp, bot, user_id, text="/closeshift")
    await send(main.dp, bot, user_id, photo_file_id="sales_photo")
    await send(main.dp, bot, user_id, photo_file_id="cash_photo")
    await send(main.dp, bot, user_id, text=cash_sales)
    await send(main.dp, bot, user_id, text=card_sales)
    await send(main.dp, bot, user_id, text=other)
    return await send(main.dp, bot, user_id, text=actual)


async def test_openshift_requires_kassir_role(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert sent == []


async def test_first_shift_asks_manual_opening_balance(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert "birinchi smenangiz" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="500000")
    assert "500000" in sent[0].text


async def test_openshift_twice_same_day_does_not_duplicate(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await send(main.dp, bot, 111, text="/openshift")
    assert "allaqachon ochilgan" in sent[0].text.lower()


async def test_expense_requires_open_shift(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)

    sent = await send(main.dp, bot, 111, text="/expense")
    assert "avval /openshift" in sent[0].text.lower()


async def test_expense_full_flow_no_anomaly(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await send(main.dp, bot, 111, text="/expense")
    assert "kategoriyasini" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="🚕 Taxi")
    assert "summasini" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="65000")
    assert "izoh" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="➖ O'tkazib yuborish")
    assert "qayd etildi" in sent[0].text.lower()

    from services import cash_expense
    from services import cash_shift

    shift = cash_shift.get_open_shift(111, __import__("datetime").date.today().isoformat())
    assert cash_expense.total_expenses_for_shift(shift["id"]) == 65000


async def test_expense_anomaly_requires_reason(bot_dp):
    main, bot = bot_dp
    from repositories import cash_shifts as repo

    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")
    shift = repo.get_open_shift(111, __import__("datetime").date.today().isoformat())

    for i, amount in enumerate((60_000,) * 7):
        repo.add_expense(shift["id"], 111, "Filial-1", "taxi", amount, None, f"2020-01-{10 + i}")

    await send(main.dp, bot, 111, text="/expense")
    await send(main.dp, bot, 111, text="🚕 Taxi")
    sent = await send(main.dp, bot, 111, text="180000")
    assert "sezilarli yuqori" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="Mijoz uzoqda edi")
    assert "qayd etildi" in sent[0].text.lower()


async def test_closeshift_clean_close(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await _close_shift_happy_path(main, bot, 111)
    assert "KASSA — KUN YAKUNI" in sent[0].text
    assert "🟢 Toza yopildi" in sent[0].text


async def test_closeshift_within_tolerance(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    sent = await _close_shift_happy_path(main, bot, 111, actual="99990")
    assert "🟡 Tolerance ichida" in sent[0].text


async def test_closeshift_recheck_then_success(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await send(main.dp, bot, 111, text="50000")  # 50_000 farq, tolerance 20_000dan katta
    assert "qayta tekshiring" in sent[0].text.lower()
    assert "Qolgan urinishlar: 2" in sent[0].text

    # Qayta urinishda rasm qayta so'ralmaydi — to'g'ridan-to'g'ri raqamlar
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    sent = await send(main.dp, bot, 111, text="0")
    sent = await send(main.dp, bot, 111, text="100000")
    assert "🟢 Toza yopildi" in sent[0].text


async def test_closeshift_escalates_to_supervisor_after_retry_limit(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    await send(main.dp, bot, 111, text="/closeshift")
    await send(main.dp, bot, 111, photo_file_id="sales_photo")
    await send(main.dp, bot, 111, photo_file_id="cash_photo")
    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="50000")  # attempt 1: recheck

    await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="50000")  # attempt 2: recheck

    sent = await send(main.dp, bot, 111, text="100000")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="0")
    sent = await send(main.dp, bot, 111, text="50000")  # attempt 3: escalates

    kassir_messages = [m for m in sent if getattr(m, "chat_id", None) == 111]
    assert "yuborildi" in kassir_messages[0].text.lower()

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_messages) == 1
    assert "tekshiruvi kerak" in founder_messages[0].text.lower()


async def test_supervisor_approve_finalizes_and_notifies_kassir(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    for _ in range(3):
        await send(main.dp, bot, 111, text="/closeshift")
        photo_needed = _  == 0
        if photo_needed:
            await send(main.dp, bot, 111, photo_file_id="sales_photo")
            await send(main.dp, bot, 111, photo_file_id="cash_photo")
        await send(main.dp, bot, 111, text="100000")
        await send(main.dp, bot, 111, text="0")
        await send(main.dp, bot, 111, text="0")
        await send(main.dp, bot, 111, text="50000")

    shift = cash_shift.get_open_shift(111, __import__("datetime").date.today().isoformat())
    assert shift["status"] == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"cashshift_approve:{shift['id']}", target_chat_id=FOUNDER_ID
    )
    kassir_messages = [m for m in sent if getattr(m, "chat_id", None) == 111]
    assert "tasdiqlandi" in kassir_messages[0].text.lower()

    updated = cash_shift.get_shift(shift["id"])
    assert updated["status"] == cash_shift.STATUS_APPROVED_BY_SUPERVISOR


async def test_non_supervisor_cannot_approve(bot_dp):
    main, bot = bot_dp
    from services import cash_shift
    _make_kassir(111)
    await _open_shift(main, bot, 111, "0")

    for i in range(3):
        await send(main.dp, bot, 111, text="/closeshift")
        if i == 0:
            await send(main.dp, bot, 111, photo_file_id="sales_photo")
            await send(main.dp, bot, 111, photo_file_id="cash_photo")
        await send(main.dp, bot, 111, text="100000")
        await send(main.dp, bot, 111, text="0")
        await send(main.dp, bot, 111, text="0")
        await send(main.dp, bot, 111, text="50000")

    shift = cash_shift.get_open_shift(111, __import__("datetime").date.today().isoformat())

    _make_kassir(222, branch="Filial-2")
    await send_callback(
        main.dp, bot, 222, data=f"cashshift_approve:{shift['id']}", target_chat_id=FOUNDER_ID
    )

    updated = cash_shift.get_shift(shift["id"])
    assert updated["status"] == cash_shift.STATUS_NEEDS_SUPERVISOR_APPROVAL


async def test_cashsummary_self_view(bot_dp):
    main, bot = bot_dp
    _make_kassir(111)
    await _open_shift(main, bot, 111, "500000")

    sent = await send(main.dp, bot, 111, text="/cashsummary")
    assert "KASSA — KUN YAKUNI" in sent[0].text
