from datetime import datetime

import pytest
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from config import FOUNDER_ID
from repositories import suppliers as suppliers_repo
from services import messages as messages_catalog
from tests.bot_harness import send

pytestmark = pytest.mark.anyio

_DENIAL_TEXTS = {
    messages_catalog.GENERIC_DENIAL,
    messages_catalog.CASH_FINANCE_DENIAL,
    messages_catalog.MANAGEMENT_DENIAL,
    messages_catalog.REPEAT_OFFENDER_DENIAL,
}


def _assert_denied(sent) -> None:
    assert len(sent) == 1, sent
    assert sent[0].text in _DENIAL_TEXTS, sent[0].text


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_openai_json_reply(bot_dp, text="Rahmat!"):
    import json
    from types import SimpleNamespace

    main, _ = bot_dp

    async def fake_create(**kwargs):
        return SimpleNamespace(
            output_text=json.dumps(
                {"reply": text}
                | {
                    k: None
                    for k in (
                        "company_name",
                        "region",
                        "contact_name",
                        "phone",
                        "product_name",
                        "price",
                        "discount",
                        "minimum_order",
                        "delivery_time",
                        "payment_type",
                        "return_terms",
                    )
                }
            )
        )

    return fake_create


async def test_invitesupplier_is_founder_only(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, user_id=999999, text="/invitesupplier")
    _assert_denied(sent)


async def test_founder_can_create_supplier_invite_link(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/invitesupplier Fresh Ferma")
    assert any("Fresh Ferma" not in (m.text or "") or "havolasi" in (m.text or "") for m in sent)
    assert any("https://t.me/" in (m.text or "") for m in sent)


async def test_start_with_supplier_token_claims_and_greets(bot_dp):
    main, bot = bot_dp

    token = suppliers_repo.create_invite("Test MCHJ", created_by=FOUNDER_ID)
    sent = await send(main.dp, bot, 424242, text=f"/start {token}")

    texts = [m.text for m in sent]
    assert any("Assalomu alaykum" in (t or "") for t in texts)
    assert suppliers_repo.get_supplier_by_telegram_id(424242) is not None


async def test_supplier_free_text_routes_to_ai(bot_dp, monkeypatch):
    main, bot = bot_dp

    token = suppliers_repo.create_invite(None, created_by=FOUNDER_ID)
    await send(main.dp, bot, 555, text=f"/start {token}")

    monkeypatch.setattr(
        main.openai_client.responses, "create", _fake_openai_json_reply(bot_dp, "Ajoyib, davom etamiz!")
    )

    sent = await send(main.dp, bot, 555, text="Bizda kartoshka bor, 3000 so'm")
    texts = [m.text for m in sent]
    assert "Ajoyib, davom etamiz!" in texts


async def test_stranger_free_text_is_not_treated_as_supplier(bot_dp):
    main, bot = bot_dp

    # Hech qachon taklif olmagan, xodim ham bo'lmagan foydalanuvchi —
    # supplier_chat_bot uni umuman ushlamasligi kerak.
    sent = await send(main.dp, bot, 777, text="Salom, narxlaringiz qanday?")
    assert sent == []


async def test_group_message_never_triggers_supplier_flow(bot_dp, monkeypatch):
    """Saturn umumiy guruhida (chat.type != private) ta'minotchi bo'lgan
    foydalanuvchi yozsa ham, bot bilan savdolashuv boshlanmasligi kerak.
    """
    import supplier_chat_bot

    token = suppliers_repo.create_invite(None, created_by=FOUNDER_ID)
    await send(bot_dp[0].dp, bot_dp[1], 555, text=f"/start {token}")

    group_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=-100123, type="group"),
        text="Bizda kartoshka bor",
        from_user=TgUser(id=555, is_bot=False, first_name="Test"),
    )

    assert await supplier_chat_bot.is_supplier_text(group_message) is False


async def test_supplierreport_requires_valid_id(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/supplierreport 9999")
    texts = [m.text for m in sent]
    assert any("topilmadi" in (t or "") for t in texts)
