from types import SimpleNamespace

import pytest

import company_time
from config import FOUNDER_ID
from repositories import cash_shifts as cash_shifts_repo
from repositories import supplier_purchases as supplier_purchases_repo
from services import shift_deficiency, supplier_purchase
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResponses:
    def __init__(self, output_text=None, error=None):
        self._output_text = output_text
        self._error = error

    async def create(self, **kwargs):
        if self._error:
            raise self._error
        return SimpleNamespace(output_text=self._output_text)


class _FakeClient:
    def __init__(self, output_text=None, error=None):
        self.responses = _FakeResponses(output_text, error)


def _make_taminotchi(user_id: int) -> None:
    from roles import set_role

    set_role(user_id, "taminotchi", set_by=FOUNDER_ID)


def _open_shift(employee_id: int, branch: str, shift_date: str) -> dict:
    return cash_shifts_repo.open_shift(employee_id, branch, shift_date, opening_balance=0, tolerance=20000)


# ------------------------------------------------------- services/supplier_purchase --


def test_should_check_price_increase_true_at_20_percent_threshold():
    assert supplier_purchase.should_check_price_increase(12000, 10000) is True


def test_should_check_price_increase_false_below_threshold():
    assert supplier_purchase.should_check_price_increase(11000, 10000) is False


def test_should_check_price_increase_false_on_decrease():
    assert supplier_purchase.should_check_price_increase(9000, 10000) is False


def test_should_check_price_increase_false_on_unchanged():
    assert supplier_purchase.should_check_price_increase(10000, 10000) is False


def test_should_check_price_increase_false_when_no_history():
    assert supplier_purchase.should_check_price_increase(50000, None) is False


async def test_check_price_spike_true_when_ai_flags():
    client = _FakeClient(output_text="HA")
    assert await supplier_purchase.check_price_spike(client, "Pomidor", 10000, 15000) is True


async def test_check_price_spike_false_when_ai_says_no():
    client = _FakeClient(output_text="YOQ")
    assert await supplier_purchase.check_price_spike(client, "Pomidor", 10000, 15000) is False


async def test_check_price_spike_fail_safe_on_error():
    client = _FakeClient(error=RuntimeError("API xatosi"))
    assert await supplier_purchase.check_price_spike(client, "Pomidor", 10000, 15000) is False


async def test_check_price_spike_fail_safe_on_ambiguous_response():
    client = _FakeClient(output_text="Bilmadim")
    assert await supplier_purchase.check_price_spike(client, "Pomidor", 10000, 15000) is False


def test_record_purchase_accepts_quantity_above_any_requested_amount():
    purchase_id = supplier_purchase.record_purchase("Pomidor", 105.7, "kg", 12000, 999)
    assert purchase_id is not None
    row = supplier_purchases_repo.get_price_history("Pomidor", "kg")
    assert row["quantity"] == 105.7


def test_record_purchase_rejects_non_positive_quantity():
    assert supplier_purchase.record_purchase("Pomidor", 0, "kg", 12000, 999) is None
    assert supplier_purchase.record_purchase("Pomidor", -5, "kg", 12000, 999) is None


def test_record_purchase_rejects_unknown_unit():
    assert supplier_purchase.record_purchase("Pomidor", 10, "tonna", 12000, 999) is None


# ------------------------------------------------------------------- /xarid bot flow --


async def test_xarid_accepts_real_quantity_above_requested_and_shows_total(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    shift = _open_shift(1, "Filial-1", today)
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 100, "kg")

    await send(main.dp, bot, 777, text="/xarid")
    sent = await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    assert "Kerak: 100 kg" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 777, text="105.7")
    assert "Birlik narxini kiriting" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 777, text="12000")
    combined = " ".join(t for t in texts(sent) if t)
    assert "105.7 kg × 12 000 = 1 268 400" in combined
    assert "Umumiy bozorlik: 1 268 400" in combined


async def test_xarid_unchanged_price_button_reuses_last_price(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    supplier_purchases_repo.add_purchase("Pomidor", 5, "kg", 10000, 777, "2020-01-01", False, None)
    shift = _open_shift(1, "Filial-1", today)
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 20, "kg")

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="20")
    assert "Oxirgi narx: 10 000" in " ".join(t for t in texts(sent) if t)

    sent = await send_callback(main.dp, bot, 777, data="sup_price_same", target_chat_id=777)
    assert "20 kg × 10 000 = 200 000" in " ".join(t for t in texts(sent) if t)


async def test_xarid_new_price_below_threshold_does_not_call_ai(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    supplier_purchases_repo.add_purchase("Pomidor", 5, "kg", 10000, 777, "2020-01-01", False, None)
    shift = _open_shift(1, "Filial-1", today)
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 20, "kg")

    async def _fail_if_called(**kwargs):
        raise AssertionError("AI chaqirilmasligi kerak edi (<20% oshish)")

    monkeypatch.setattr(main.openai_client.responses, "create", _fail_if_called)

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="20")
    await send_callback(main.dp, bot, 777, data="sup_price_new", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="11500")  # 15% oshish

    combined = " ".join(t for t in texts(sent) if t)
    assert "odatdagidan ancha oshgan" not in combined
    assert "230 000" in combined


async def test_xarid_price_decrease_does_not_call_ai(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    supplier_purchases_repo.add_purchase("Pomidor", 5, "kg", 10000, 777, "2020-01-01", False, None)
    shift = _open_shift(1, "Filial-1", today)
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 20, "kg")

    async def _fail_if_called(**kwargs):
        raise AssertionError("AI chaqirilmasligi kerak edi (narx pasaydi)")

    monkeypatch.setattr(main.openai_client.responses, "create", _fail_if_called)

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="20")
    await send_callback(main.dp, bot, 777, data="sup_price_new", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="8000")

    combined = " ".join(t for t in texts(sent) if t)
    assert "odatdagidan ancha oshgan" not in combined
    assert "160 000" in combined


async def test_xarid_price_spike_asks_question_and_saves_reason(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    supplier_purchases_repo.add_purchase("Pomidor", 5, "kg", 10000, 777, "2020-01-01", False, None)
    shift = _open_shift(1, "Filial-1", today)
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 20, "kg")

    async def _fake_create(**kwargs):
        return SimpleNamespace(output_text="HA")

    monkeypatch.setattr(main.openai_client.responses, "create", _fake_create)

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="20")
    await send_callback(main.dp, bot, 777, data="sup_price_new", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="15000")  # 50% oshish
    assert "odatdagidan ancha oshgan" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, 777, text="Bozorda hosil kam bo'ldi")
    assert "300 000" in " ".join(t for t in texts(sent) if t)

    row = supplier_purchases_repo.get_price_history("Pomidor", "kg")
    assert row["price_flagged"] == 1
    assert row["price_flag_reason"] == "Bozorda hosil kam bo'ldi"


async def test_xarid_ai_failure_is_fail_safe(bot_dp, monkeypatch):
    main, bot = bot_dp
    _make_taminotchi(777)
    today = company_time.today().isoformat()
    supplier_purchases_repo.add_purchase("Pomidor", 5, "kg", 10000, 777, "2020-01-01", False, None)
    shift = _open_shift(1, "Filial-1", today)
    shift_deficiency.add_market_item(shift["id"], 1, "Pomidor", 20, "kg")

    async def _boom(**kwargs):
        raise RuntimeError("API xatosi")

    monkeypatch.setattr(main.openai_client.responses, "create", _boom)

    await send(main.dp, bot, 777, text="/xarid")
    await send_callback(main.dp, bot, 777, data="sup_pick:0", target_chat_id=777)
    await send(main.dp, bot, 777, text="20")
    await send_callback(main.dp, bot, 777, data="sup_price_new", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="15000")

    combined = " ".join(t for t in texts(sent) if t)
    assert "odatdagidan ancha oshgan" not in combined
    assert "300 000" in combined

    row = supplier_purchases_repo.get_price_history("Pomidor", "kg")
    assert row["price_flagged"] == 0


async def test_xarid_add_ad_hoc_product_not_in_original_list(bot_dp):
    main, bot = bot_dp
    _make_taminotchi(777)

    await send(main.dp, bot, 777, text="/xarid")
    sent = await send_callback(main.dp, bot, 777, data="sup_add_product", target_chat_id=777)
    assert "Mahsulot nomini kiriting" in " ".join(t for t in texts(sent) if t)

    await send(main.dp, bot, 777, text="Sham")
    await send(main.dp, bot, 777, text="4")
    await send_callback(main.dp, bot, 777, data="sup_new_unit:dona", target_chat_id=777)
    sent = await send(main.dp, bot, 777, text="5000")

    combined = " ".join(t for t in texts(sent) if t)
    assert "Sham — 4 dona × 5 000 = 20 000" in combined
    assert "Umumiy bozorlik: 20 000" in combined
