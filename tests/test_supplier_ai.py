import json
from types import SimpleNamespace

import pytest

from repositories import suppliers as suppliers_repo
from services import supplier_ai

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResponses:
    def __init__(self, output_text=None, error=None, capture=None):
        self._output_text = output_text
        self._error = error
        self._capture = capture

    async def create(self, **kwargs):
        if self._capture is not None:
            self._capture.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(output_text=self._output_text)


class _FakeClient:
    def __init__(self, output_text=None, error=None, capture=None):
        self.responses = _FakeResponses(output_text, error, capture)


def _make_supplier(telegram_user_id=1):
    token = suppliers_repo.create_invite(None, created_by=111)
    return suppliers_repo.claim_invite(token, telegram_user_id=telegram_user_id)


async def test_handle_supplier_message_persists_reply_and_offer():
    supplier = _make_supplier()
    ai_json = json.dumps(
        {
            "reply": "Rahmat! Narxni yozib qo'ydim.",
            "company_name": "Fresh Ferma",
            "region": "Toshkent",
            "contact_name": None,
            "phone": None,
            "product_name": "Kartoshka",
            "price": "3000",
            "discount": None,
            "minimum_order": None,
            "delivery_time": None,
            "payment_type": None,
            "return_terms": None,
        }
    )
    client = _FakeClient(output_text=ai_json)

    reply = await supplier_ai.handle_supplier_message(client, supplier, "Kartoshka 3000 so'm")

    assert reply == "Rahmat! Narxni yozib qo'ydim."

    updated = suppliers_repo.get_supplier(supplier["id"])
    assert updated["company_name"] == "Fresh Ferma"
    assert updated["region"] == "Toshkent"

    offers = suppliers_repo.list_offers(supplier["id"])
    assert offers[0]["product_name"] == "Kartoshka"
    assert offers[0]["price"] == "3000"

    history = suppliers_repo.get_recent_messages(supplier["id"])
    assert [h["role"] for h in history] == ["user", "assistant"]


async def test_handle_supplier_message_never_fabricates_unstated_fields():
    supplier = _make_supplier()
    ai_json = json.dumps(
        {
            "reply": "Tushundim, davom etamiz.",
            "company_name": None,
            "region": None,
            "contact_name": None,
            "phone": None,
            "product_name": None,
            "price": None,
            "discount": None,
            "minimum_order": None,
            "delivery_time": None,
            "payment_type": None,
            "return_terms": None,
        }
    )
    client = _FakeClient(output_text=ai_json)

    await supplier_ai.handle_supplier_message(client, supplier, "Salom")

    assert suppliers_repo.list_offers(supplier["id"]) == []
    updated = suppliers_repo.get_supplier(supplier["id"])
    assert updated["company_name"] is None


async def test_handle_supplier_message_falls_back_on_openai_error():
    supplier = _make_supplier()
    client = _FakeClient(error=RuntimeError("API xatosi"))

    reply = await supplier_ai.handle_supplier_message(client, supplier, "Salom")

    assert "texnik xatolik" in reply
    history = suppliers_repo.get_recent_messages(supplier["id"])
    assert history[-1]["role"] == "assistant"


async def test_handle_supplier_message_falls_back_on_invalid_json():
    supplier = _make_supplier()
    client = _FakeClient(output_text="bu JSON emas, oddiy matn")

    reply = await supplier_ai.handle_supplier_message(client, supplier, "Salom")

    assert reply == supplier_ai._FALLBACK_REPLY


async def test_prompt_never_includes_other_suppliers_data():
    """Maxfiylik: bitta ta'minotchining suhbat konteksti boshqa
    ta'minotchining ma'lumotini o'z ichiga OLMASLIGI kerak."""
    supplier_a = _make_supplier(telegram_user_id=1)
    supplier_b = _make_supplier(telegram_user_id=2)

    suppliers_repo.update_supplier_profile(supplier_b["id"], company_name="Maxfiy Raqib MCHJ")
    suppliers_repo.upsert_offer(supplier_b["id"], "Kartoshka", price="1234-MAXFIY")
    suppliers_repo.add_message(supplier_b["id"], "user", "Bizning maxfiy narximiz 1234-MAXFIY")

    captured = []
    client = _FakeClient(
        output_text=json.dumps({"reply": "OK"} | {k: None for k in (
            "company_name", "region", "contact_name", "phone", "product_name",
            "price", "discount", "minimum_order", "delivery_time", "payment_type", "return_terms",
        )}),
        capture=captured,
    )

    await supplier_ai.handle_supplier_message(client, supplier_a, "Salom, narxlaringiz qanday?")

    sent_input = captured[0]["input"]
    assert "Maxfiy Raqib" not in sent_input
    assert "1234-MAXFIY" not in sent_input


def test_compare_offers_for_product_includes_all_suppliers_for_founder():
    supplier_a = _make_supplier(telegram_user_id=1)
    supplier_b = _make_supplier(telegram_user_id=2)
    suppliers_repo.upsert_offer(supplier_a["id"], "Piyoz", price="1000")
    suppliers_repo.upsert_offer(supplier_b["id"], "Piyoz", price="900")

    data = supplier_ai.compare_offers_for_product("Piyoz")

    assert len(data["supplier_offers"]) == 2
    assert data["market_reference"] == []


async def test_generate_founder_summary_stores_and_returns_text():
    supplier = _make_supplier()
    suppliers_repo.upsert_offer(supplier["id"], "Sabzi", price="1500")
    client = _FakeClient(output_text="Xulosa: yaxshi taklif, davom ettirish tavsiya etiladi.")

    summary = await supplier_ai.generate_founder_summary(client, supplier)

    assert "tavsiya etiladi" in summary
    stored = suppliers_repo.get_latest_founder_summary(supplier["id"])
    assert stored["summary_text"] == summary
