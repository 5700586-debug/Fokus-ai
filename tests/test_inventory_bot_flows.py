from datetime import timedelta

import pytest

import company_time
from config import FOUNDER_ID
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_savdo_boshligi(user_id: int, branch: str = "Filial-1") -> None:
    from roles import set_role
    import employees

    set_role(user_id, "savdo_boshligi", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id,
        {
            "familiya": "Boshliqov", "ism": "Karim", "otasining_ismi": "Vali",
            "branch": branch, "role_key": "savdo_boshligi", "contacts": [],
        },
    )


def _yesterday() -> str:
    return (company_time.today() - timedelta(days=1)).isoformat()


async def test_invsnapshot_requires_savdo_boshligi_role(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, 111, text="/invsnapshot")
    assert sent == []


async def test_first_snapshot_no_previous_no_causes(bot_dp):
    main, bot = bot_dp
    _make_savdo_boshligi(111)

    sent = await send(main.dp, bot, 111, text="/invsnapshot")
    assert "rasmga olib" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, photo_file_id="inv_photo_1")
    assert "summasini" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="120000000")
    assert "OMBOR — KUNLIK NAZORAT" in sent[0].text
    assert "🟢 Normal" in sent[0].text


async def test_duplicate_snapshot_same_day(bot_dp):
    main, bot = bot_dp
    _make_savdo_boshligi(111)

    await send(main.dp, bot, 111, text="/invsnapshot")
    await send(main.dp, bot, 111, photo_file_id="p1")
    await send(main.dp, bot, 111, text="120000000")

    await send(main.dp, bot, 111, text="/invsnapshot")
    await send(main.dp, bot, 111, photo_file_id="p2")
    sent = await send(main.dp, bot, 111, text="999999999")
    assert "allaqachon yuborilgan" in sent[0].text.lower()


async def test_variance_within_threshold_needs_review(bot_dp):
    main, bot = bot_dp
    _make_savdo_boshligi(111)
    from repositories import inventory as inv_repo

    inv_repo.create_snapshot(
        "Filial-1", _yesterday(), reported_by_employee_id=111,
        total_inventory_value=120_000_000, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )

    await send(main.dp, bot, 111, text="/invsnapshot")
    await send(main.dp, bot, 111, photo_file_id="p1")
    sent = await send(main.dp, bot, 111, text="120500000")  # +500_000, threshold ichida

    sent = await send(main.dp, bot, 111, text="➖ Boshqa")
    await send(main.dp, bot, 111, text="0")
    sent = await send(main.dp, bot, 111, text="➖ O'tkazib yuborish")
    sent = await send(main.dp, bot, 111, text="Yo'q")

    assert "🟡 Tekshirish kerak" in sent[0].text


async def test_full_variance_explanation_flow_with_urgent_push(bot_dp):
    main, bot = bot_dp
    _make_savdo_boshligi(111)
    from repositories import inventory as inv_repo

    inv_repo.create_snapshot(
        "Filial-1", _yesterday(), reported_by_employee_id=111,
        total_inventory_value=120_000_000, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )

    await send(main.dp, bot, 111, text="/invsnapshot")
    await send(main.dp, bot, 111, photo_file_id="p1")
    sent = await send(main.dp, bot, 111, text="122400000")  # +2_400_000, threshold(1_000_000)dan katta
    assert "farqning sababi" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="➖ Boshqa")
    assert "summani" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="0")
    assert "izoh" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="Hali aniqlanmagan")
    assert "yana sabab" in sent[0].text.lower()

    sent = await send(main.dp, bot, 111, text="Yo'q")

    reporter_messages = [m for m in sent if getattr(m, "chat_id", None) == 111]
    assert "🔴 Zudlik bilan tekshirish" in reporter_messages[0].text

    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_messages) == 1
    assert "voydod" in founder_messages[0].text.lower()

    from services import inventory_snapshot as inv

    snapshot = inv_repo.get_snapshot_for_date("Filial-1", company_time.today().isoformat())
    assert snapshot["status"] == inv.STATUS_URGENT_REVIEW

    resolve_sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"invvariance_resolve:{snapshot['id']}", target_chat_id=FOUNDER_ID
    )
    reporter_notif = [m for m in resolve_sent if getattr(m, "chat_id", None) == 111]
    assert "tekshirildi va yopildi" in reporter_notif[0].text.lower()


async def test_non_supervisor_cannot_resolve_variance(bot_dp):
    main, bot = bot_dp
    from repositories import inventory as inv_repo

    snapshot = inv_repo.create_snapshot(
        "Filial-1", "2020-01-01", reported_by_employee_id=111,
        total_inventory_value=100, previous_inventory_value=None,
        gross_difference=None, threshold=1_000_000, photo_reference=None,
    )

    _make_savdo_boshligi(222, branch="Filial-2")
    await send_callback(
        main.dp, bot, 222, data=f"invvariance_resolve:{snapshot['id']}", target_chat_id=FOUNDER_ID
    )

    unchanged = inv_repo.get_snapshot(snapshot["id"])
    assert unchanged["status"] == "pending"


async def test_inventorysummary_self_view(bot_dp):
    main, bot = bot_dp
    _make_savdo_boshligi(111)

    await send(main.dp, bot, 111, text="/invsnapshot")
    await send(main.dp, bot, 111, photo_file_id="p1")
    await send(main.dp, bot, 111, text="120000000")

    sent = await send(main.dp, bot, 111, text="/inventorysummary")
    assert "OMBOR — KUNLIK NAZORAT" in sent[0].text


async def test_inventorysummary_founder_can_view_any_branch(bot_dp):
    main, bot = bot_dp
    _make_savdo_boshligi(111, branch="Filial-9")

    await send(main.dp, bot, 111, text="/invsnapshot")
    await send(main.dp, bot, 111, photo_file_id="p1")
    await send(main.dp, bot, 111, text="120000000")

    sent = await send(main.dp, bot, FOUNDER_ID, text="/inventorysummary Filial-9")
    assert "OMBOR — KUNLIK NAZORAT" in sent[0].text


async def test_stranger_cannot_view_inventorysummary_by_branch(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, 999999, text="/inventorysummary Filial-1")
    assert sent == []
