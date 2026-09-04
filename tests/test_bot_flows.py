import pytest

from config import FOUNDER_ID
from services import messages as messages_catalog
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio

_DENIAL_TEXTS = {
    messages_catalog.GENERIC_DENIAL,
    messages_catalog.CASH_FINANCE_DENIAL,
    messages_catalog.MANAGEMENT_DENIAL,
    messages_catalog.REPEAT_OFFENDER_DENIAL,
}


def _assert_denied(sent) -> None:
    """Ruxsatsiz urinish endi jim emas — qisqa "Saturncha" javob
    yuboriladi (qarang ``services/messages.py``)."""
    assert len(sent) == 1, sent
    assert sent[0].text in _DENIAL_TEXTS, sent[0].text


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _complete_onboarding(main, bot, user_id: int, token: str, familiya: str = "Familiyev") -> None:
    """Invite token orqali onboardingni familiyadan tortib tasdiqlash
    ekranigacha to'liq to'ldiradi va yuboradi (bir nechta testda
    qayta ishlatiladi).
    """
    await send(main.dp, bot, user_id, text=f"/start {token}")
    await send(main.dp, bot, user_id, text=familiya)
    await send(main.dp, bot, user_id, text="Ism")
    await send(main.dp, bot, user_id, text="Ota")
    await send(main.dp, bot, user_id, text="01.05.1995")
    await send(main.dp, bot, user_id, text="Erkak")
    await send(main.dp, bot, user_id, text="+998901234567")
    await send(main.dp, bot, user_id, text="Kontakt Bir")
    await send(main.dp, bot, user_id, text="+998901111111")
    await send(main.dp, bot, user_id, text="Aka")
    await send(main.dp, bot, user_id, text="Kontakt Ikki")
    await send(main.dp, bot, user_id, text="+998902222222")
    await send(main.dp, bot, user_id, text="Opa")
    await send(main.dp, bot, user_id, text="Turmush qurmagan")
    await send(main.dp, bot, user_id, text="Toshkent")
    await send(main.dp, bot, user_id, text="Chilonzor MFY, 12-uy")
    await send(main.dp, bot, user_id, text="01.08.2026")
    await send(main.dp, bot, user_id, text="09:00-18:00")
    await send(main.dp, bot, user_id, text="🔄 Ba'zan ishlay olaman")
    await send(main.dp, bot, user_id, text="✅ Ha, roziman")
    await send(main.dp, bot, user_id, text="✅ Ha, roziman")
    await send(main.dp, bot, user_id, text="1–2 yil")
    await send(main.dp, bot, user_id, text="Yaxshi jamoa bor")
    await send(main.dp, bot, user_id, text="➖ O'tkazib yuborish")
    await send(main.dp, bot, user_id, text="Yo'q")
    await send(main.dp, bot, user_id, text="Kontakt Bir")
    await send(main.dp, bot, user_id, photo_file_id="photo_abc")
    await send(main.dp, bot, user_id, text="➖ O'tkazib yuborish")
    await send(main.dp, bot, user_id, text="✅ Ma'lumotlar to'g'ri")


async def test_founder_start_greets_founder(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")

    assert len(sent) == 1
    assert sent[0].text == (
        "Assalomu alaykum, Muhammadiy! 👋\n"
        "Tadbirkorning vaqti qadrli. Ishlarni tez va sodda boshqaramiz."
    )


async def test_founder_start_shows_new_greeting_and_seven_menu_buttons(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")

    assert sent[0].text == (
        "Assalomu alaykum, Muhammadiy! 👋\n"
        "Tadbirkorning vaqti qadrli. Ishlarni tez va sodda boshqaramiz."
    )
    assert "Founder" not in sent[0].text
    assert "Asoschi" not in sent[0].text

    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert buttons == [
        "👤 Xodim qo'shish",
        "📢 Ishga e'lon berish",
        "👥 Xodimlar",
        "🏬 Do'konlar",
        "💰 Smenalarni ko'rish",
        "🚨 Bugungi muammolar",
        "⚙️ Sozlamalar",
    ]


async def test_stores_button_shows_one_button_per_branch(bot_dp):
    main, bot = bot_dp
    from config import RECRUITING_BRANCH_NAMES

    sent = await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")

    assert len(sent) == 1
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    for branch in RECRUITING_BRANCH_NAMES:
        assert f"📍 {branch}" in buttons
    assert "⬅️ Orqaga" in buttons
    assert "Ruxsat etilgan foydalanuvchilar" not in sent[0].text


async def test_stores_back_button_returns_founder_menu(bot_dp):
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="🏬 Do'konlar")
    sent = await send(main.dp, bot, FOUNDER_ID, text="⬅️ Orqaga")

    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "🏬 Do'konlar" in buttons


async def test_employees_button_shows_empty_placeholder_when_no_users(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="👥 Xodimlar")

    assert len(sent) == 1
    assert "Ro'yxat bo'sh" in sent[0].text
    assert "🏬 Do'konlar" not in sent[0].text


async def test_employees_button_shows_friendly_name_not_user_id(bot_dp):
    main, bot = bot_dp
    from roles import set_role
    import employees

    set_role(222, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        222,
        {
            "familiya": "Karimov", "ism": "Bek", "otasining_ismi": "Alik",
            "branch": "Filial-1", "role_key": "kassir", "contacts": [],
        },
    )
    employees.approve_profile(222, approved_by=FOUNDER_ID)

    sent = await send(main.dp, bot, FOUNDER_ID, text="👥 Xodimlar")

    buttons = [btn.text for row in sent[0].reply_markup.inline_keyboard for btn in row]
    assert any("Karimov Bek" in text and "Kassir" in text for text in buttons)
    assert not any("222" in text for text in buttons)


async def test_tapping_employee_shows_full_read_only_card(bot_dp):
    from tests.bot_harness import send_callback

    main, bot = bot_dp
    from roles import set_role
    import employees

    set_role(222, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        222,
        {
            "familiya": "Karimov", "ism": "Bek", "otasining_ismi": "Alik",
            "branch": "Filial-1", "role_key": "kassir", "contacts": [],
        },
    )
    employees.approve_profile(222, approved_by=FOUNDER_ID)

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data="founderux_emp:222", target_chat_id=FOUNDER_ID
    )

    texts = [getattr(m, "text", None) for m in sent]
    assert any(t and "Karimov Bek Alik" in t for t in texts)


async def test_add_employee_button_asks_role_with_existing_role_buttons(bot_dp):
    main, bot = bot_dp
    from roles import ROLES

    sent = await send(main.dp, bot, FOUNDER_ID, text="👤 Xodim qo'shish")

    assert sent[0].text == "Kim bo'lib ishlaydi?"
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    for key, name in ROLES.items():
        if key != "founder":
            assert name in buttons
    assert "⬅️ Orqaga" in buttons


async def test_add_employee_role_and_branch_selection_produces_invite_link(bot_dp):
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="👤 Xodim qo'shish")
    sent = await send(main.dp, bot, FOUNDER_ID, text="Kassir")
    assert sent[0].text == "Qaysi do'konda ishlaydi?"

    rows = sent[0].reply_markup.keyboard
    assert [b.text for b in rows[0]] == ["SATURN Charhiy", "SATURN Derizlik"]
    assert [b.text for b in rows[1]] == ["SATURN Navoiy", "SATURN Shafran"]
    assert [b.text for b in rows[2]] == ["⬅️ Orqaga"]

    sent = await send(main.dp, bot, FOUNDER_ID, text="SATURN Charhiy")
    assert sent[0].text.startswith("✅ Link tayyor\n")
    assert "https://t.me/" in sent[0].text
    assert "invite" not in sent[0].text.lower()
    assert "token" not in sent[0].text.lower()
    assert "Filial-1" not in sent[0].text
    assert "Filial-2" not in sent[0].text


async def test_invite_role_buttons_are_paired_two_per_row(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="👤 Xodim qo'shish")
    rows = sent[0].reply_markup.keyboard

    # "⬅️ Orqaga" doim eng pastda, alohida qatorda.
    assert [b.text for b in rows[-1]] == ["⬅️ Orqaga"]
    # Qolgan barcha (rol) qatorlar 2 tadan (oxirgisi toq bo'lsa 1 ta bo'lishi mumkin).
    for row in rows[:-1]:
        assert len(row) in (1, 2)
    assert all(len(row) == 2 for row in rows[:-2])


async def test_stranger_start_is_rejected(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, 999999, text="/start")

    assert len(sent) == 1
    assert sent[0].text == main.STRANGER_TEXT


async def test_stranger_founder_only_commands_are_silently_ignored(bot_dp):
    main, bot = bot_dp

    for command in ("/invite", "/listusers", "/setrule x 1", "/processmonth 1 2026-01 1 1 1"):
        sent = await send(main.dp, bot, 999999, text=command)
        _assert_denied(sent)


async def test_invite_and_setrole_flow(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    assert len(sent) == 1
    assert "Taklif havolasi yaratildi" in sent[0].text
    assert "https://t.me/test_bot?start=" in sent[0].text

    token = sent[0].text.split("start=")[1].split()[0]

    sent = await send(main.dp, bot, 555, text=f"/start {token}")
    assert any("Ismingiz" in t or "F.I.Sh" in t or "Familiya" in t for t in texts(sent)), texts(sent)


async def test_command_invite_active_pending_returns_same_link_no_duplicate(bot_dp):
    """/invite ikkinchi marta bosilganda (hali muddati o'tmagan active
    havola bo'lsa) filial-bog'liq rollar uchun ham eski link qaytarilishi
    kerak — avval bu himoya faqat bir kishilik rollarga xos edi, shu
    sabab boshqa rollarda cheksiz dublikat token yaratilardi."""
    main, bot = bot_dp

    first = await send(main.dp, bot, FOUNDER_ID, text="/invite sotuvchi Chilonzor filiali")
    token1 = first[0].text.split("start=")[1].split()[0]

    second = await send(main.dp, bot, FOUNDER_ID, text="/invite sotuvchi Chilonzor filiali")
    token2 = second[0].text.split("start=")[1].split()[0]

    assert token1 == token2


async def test_command_invite_claimed_pending_explains_instead_of_dead_end(bot_dp):
    """Havola allaqachon boshqa xodim tomonidan ochilgan (claimed) bo'lsa,
    Founder qayta /invite bossa, tushunarli javob va ishlaydigan havola
    olishi kerak — bo'sh "allaqachon mavjud" degan tugagan javob emas."""
    main, bot = bot_dp

    first = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token = first[0].text.split("start=")[1].split()[0]

    await send(main.dp, bot, 777, text=f"/start {token}")

    second = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    assert len(second) == 1
    assert token in second[0].text
    assert "faqat shu havolani ochgan xodim" in second[0].text.lower()


async def test_button_invite_expired_pending_creates_fresh_link(bot_dp):
    """Tugma orqali xodim qo'shishda eski havola muddati tugagan bo'lsa,
    Founder yangi ishlaydigan link olishi kerak, dead-end emas."""
    import invites
    from db import get_connection
    from datetime import datetime, timedelta, timezone

    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="👤 Xodim qo'shish")
    sent = await send(main.dp, bot, FOUNDER_ID, text="Kassir")
    sent = await send(main.dp, bot, FOUNDER_ID, text="SATURN Charhiy")
    old_token = sent[0].text.split("start=")[1].split()[0]

    conn = get_connection()
    try:
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn.execute("UPDATE invites SET expires_at = ? WHERE token = ?", (past, old_token))
        conn.commit()
    finally:
        conn.close()

    await send(main.dp, bot, FOUNDER_ID, text="👤 Xodim qo'shish")
    sent = await send(main.dp, bot, FOUNDER_ID, text="Kassir")
    sent = await send(main.dp, bot, FOUNDER_ID, text="SATURN Charhiy")
    new_token = sent[0].text.split("start=")[1].split()[0]

    assert new_token != old_token


async def test_reopening_invite_does_not_erase_active_onboarding(bot_dp):
    """Regressiya: xodim anketa davomida bir martalik invite havolasini
    qayta bossa (masalan eski xabarni topolmay), anketa hech qachon
    o'chirilmasin va boshidan boshlanmasin — aynan joriy savol va
    tugma qayta ko'rsatilib, mavjud FSM ma'lumoti saqlanishi kerak.
    """
    main, bot = bot_dp

    import invites

    user_id = 60061
    token = invites.create_invite("kassir", "SATURN Derizlik", FOUNDER_ID)
    await send(main.dp, bot, user_id, text=f"/start {token}")
    for answer in ("Familiyev", "Ism", "Ota", "01.05.1995"):
        await send(main.dp, bot, user_id, text=answer)

    # Endi "jinsi" bosqichida -- xuddi shu havolani qayta bosadi.
    sent = await send(main.dp, bot, user_id, text=f"/start {token}")

    assert sent[0].text == "Jinsingizni tanlang:"
    rows = sent[0].reply_markup.keyboard
    assert [b.text for b in rows[0]] == ["Erkak", "Ayol"]
    assert sent[0].reply_markup.is_persistent is True

    sent = await send(main.dp, bot, user_id, text="Ayol")
    assert sent[0].text == "Asosiy telefon raqamingizni kiriting. Masalan: +998901234567"

    # Anketani oxirigacha davom ettiramiz -- ma'lumot yo'qolmagan bo'lsa,
    # bu keyingi savollar to'g'ri ketma-ketlikda kelishi va oxir-oqibat
    # yakunlanishi kerak.
    await send(main.dp, bot, user_id, text="+998901234567")
    await send(main.dp, bot, user_id, text="Kontakt Bir")
    await send(main.dp, bot, user_id, text="+998901111111")
    await send(main.dp, bot, user_id, text="Aka")
    await send(main.dp, bot, user_id, text="Kontakt Ikki")
    await send(main.dp, bot, user_id, text="+998902222222")
    await send(main.dp, bot, user_id, text="Opa")
    await send(main.dp, bot, user_id, text="Turmush qurmagan")
    await send(main.dp, bot, user_id, text="Toshkent")
    await send(main.dp, bot, user_id, text="Chilonzor MFY, 12-uy")
    await send(main.dp, bot, user_id, text="01.08.2026")
    await send(main.dp, bot, user_id, text="09:00-18:00")
    await send(main.dp, bot, user_id, text="🔄 Ba'zan ishlay olaman")
    await send(main.dp, bot, user_id, text="✅ Ha, roziman")
    await send(main.dp, bot, user_id, text="✅ Ha, roziman")
    await send(main.dp, bot, user_id, text="1–2 yil")
    await send(main.dp, bot, user_id, text="Yaxshi jamoa bor")
    await send(main.dp, bot, user_id, text="➖ O'tkazib yuborish")
    await send(main.dp, bot, user_id, text="Yo'q")
    await send(main.dp, bot, user_id, text="Kontakt Bir")
    await send(main.dp, bot, user_id, photo_file_id="photo_abc")
    await send(main.dp, bot, user_id, text="➖ O'tkazib yuborish")
    await send(main.dp, bot, user_id, text="✅ Ma'lumotlar to'g'ri")

    from employees import get_profile

    profile = get_profile(user_id)
    assert profile["status"] == "submitted"
    assert profile["familiya"] == "Familiyev"
    assert profile["ism"] == "Ism"
    assert profile["otasining_ismi"] == "Ota"
    assert profile["jinsi"] == "Ayol"


async def test_only_founder_can_assign_nazoratchi(bot_dp):
    """Bu yil kompaniyada faqat bitta nazoratchi ishlaydi va uni faqat
    asoschi tayinlay oladi — begona emas, balki ALLAQACHON ro'yxatdan
    o'tgan, boshqa roldagi xodim ham nazoratchi tayinlay olmasligini
    tekshiradi (kuchliroq tahdid modeli, shunchaki "begona"dan farqli).
    """
    main, bot = bot_dp
    from roles import get_role, set_role

    set_role(111, "kassir", set_by=FOUNDER_ID)

    sent = await send(main.dp, bot, 111, text="/setrole 222 nazoratchi")
    _assert_denied(sent)
    assert get_role(222) is None

    sent = await send(main.dp, bot, 111, text="/invite nazoratchi")
    _assert_denied(sent)

    sent = await send(main.dp, bot, FOUNDER_ID, text="/setrole 222 nazoratchi")
    assert sent[0].text.startswith("✅")
    assert get_role(222) == "nazoratchi"


async def test_second_nazoratchi_assignment_is_rejected(bot_dp):
    """Bitta nazoratchi tizimi: Founder ikkinchi nazoratchi tayinlashga
    urinsa ham, mavjud nazoratchi almashtirilmaydi (roles.set_role'dagi
    single-slot himoyasi Telegram qatlamida ham amal qilishini
    tasdiqlaydi).
    """
    main, bot = bot_dp
    from roles import get_role

    await send(main.dp, bot, FOUNDER_ID, text="/setrole 111 nazoratchi")
    assert get_role(111) == "nazoratchi"

    sent = await send(main.dp, bot, FOUNDER_ID, text="/setrole 222 nazoratchi")
    assert "allaqachon" in sent[0].text.lower()
    assert get_role(222) is None
    assert get_role(111) == "nazoratchi"


async def test_setrole_and_listusers(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/setrole 777 nazoratchi")
    assert "rol o'rnatildi" in sent[0].text.lower() or "o‘rnatildi" in sent[0].text.lower()

    sent = await send(main.dp, bot, FOUNDER_ID, text="/listusers")
    assert "777" in sent[0].text


async def test_score_requires_nazoratchi_role(bot_dp):
    main, bot = bot_dp
    from roles import set_role

    set_role(888, "haydovchi", set_by=FOUNDER_ID)

    sent = await send(main.dp, bot, 888, text="/score 1 90")
    _assert_denied(sent)

    set_role(999, "nazoratchi", set_by=FOUNDER_ID)
    sent = await send(main.dp, bot, 999, text="/score 1 90")
    assert len(sent) == 1
    assert "qayd etildi" in sent[0].text


async def test_mystars_requires_authorization(bot_dp):
    main, bot = bot_dp
    from roles import set_role

    sent = await send(main.dp, bot, 321, text="/mystars")
    assert sent == []

    set_role(321, "haydovchi", set_by=FOUNDER_ID)
    sent = await send(main.dp, bot, 321, text="/mystars")
    assert len(sent) == 1
    assert "Joriy yulduzlar" in sent[0].text


async def test_mealplan_requires_savdo_boshligi_role(bot_dp):
    main, bot = bot_dp
    from roles import set_role

    set_role(444, "savdo_boshligi", set_by=FOUNDER_ID)

    sent = await send(main.dp, bot, 444, text="/mealplan 10.08.2026 Osh")
    assert len(sent) == 1
    assert "saqlandi" in sent[0].text


async def test_marketlog_fsm_flow(bot_dp):
    main, bot = bot_dp
    from roles import set_role

    set_role(222, "taminotchi", set_by=FOUNDER_ID)

    sent = await send(main.dp, bot, 222, text="/marketlog")
    assert "Mahsulot" in sent[0].text

    sent = await send(main.dp, bot, 222, text="Kartoshka")
    assert "Nav" in sent[0].text

    for skip_reply in range(8):
        sent = await send(main.dp, bot, 222, text="➖ O'tkazib yuborish")

    assert "saqlandi" in sent[-1].text

    from services import market_observation

    observations = market_observation.recent_observations()
    assert len(observations) == 1
    assert observations[0]["product"] == "Kartoshka"


async def test_drivercheck_without_vehicle_is_rejected(bot_dp):
    main, bot = bot_dp
    from roles import set_role

    set_role(333, "haydovchi", set_by=FOUNDER_ID)

    sent = await send(main.dp, bot, 333, text="/drivercheck")
    assert "topilmadi" in sent[0].text


async def test_drivercheck_full_flow(bot_dp):
    main, bot = bot_dp
    from roles import set_role
    from repositories import vehicles as vehicles_repo

    set_role(333, "haydovchi", set_by=FOUNDER_ID)
    vehicles_repo.create_vehicle("01A777AA", "Nexia", 333)

    sent = await send(main.dp, bot, 333, text="/drivercheck")
    assert "Spidometr" in sent[0].text

    sent = await send(main.dp, bot, 333, text="1000")
    assert "tugash" in sent[0].text.lower()

    sent = await send(main.dp, bot, 333, text="➖ O'tkazib yuborish")  # end_km
    sent = await send(main.dp, bot, 333, text="➖ O'tkazib yuborish")  # exterior photo
    sent = await send(main.dp, bot, 333, text="➖ O'tkazib yuborish")  # interior photo
    sent = await send(main.dp, bot, 333, text="➖ O'tkazib yuborish")  # notes

    assert "saqlandi" in sent[-1].text


async def test_addvehicle_duplicate_plate_gives_friendly_error(bot_dp):
    """``/addvehicle`` xuddi bir davlat raqami bilan ikki marta chaqirilsa,
    repository UNIQUE constraint bosadi (``db.IntegrityError`` — SQLite'da
    ``sqlite3.IntegrityError``, Postgres'da ``psycopg2.IntegrityError``).
    Handler buni ushlab tushunarli xabar berishi kerak, umumiy
    "Kutilmagan xatolik" xabari emas (qarang: performance_bot.py).
    """
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/addvehicle 01A777AA 333")
    assert "qo'shildi" in sent[0].text

    sent = await send(main.dp, bot, FOUNDER_ID, text="/addvehicle 01A777AA 444")
    assert "allaqachon mavjud" in sent[0].text


async def test_full_onboarding_to_approval_flow(bot_dp):
    main, bot = bot_dp
    new_user_id = 55501

    invite_sent = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token = invite_sent[0].text.split("start=")[1].split()[0]

    await send(main.dp, bot, new_user_id, text=f"/start {token}")
    await send(main.dp, bot, new_user_id, text="Familiyev")
    await send(main.dp, bot, new_user_id, text="Ism")
    await send(main.dp, bot, new_user_id, text="Ota")
    await send(main.dp, bot, new_user_id, text="01.05.1995")
    await send(main.dp, bot, new_user_id, text="Erkak")
    await send(main.dp, bot, new_user_id, text="+998901234567")
    await send(main.dp, bot, new_user_id, text="Kontakt Bir")
    await send(main.dp, bot, new_user_id, text="+998901111111")
    await send(main.dp, bot, new_user_id, text="Aka")
    await send(main.dp, bot, new_user_id, text="Kontakt Ikki")
    await send(main.dp, bot, new_user_id, text="+998902222222")
    sent = await send(main.dp, bot, new_user_id, text="Opa")
    assert "Oilaviy holat" in sent[-1].text

    sent = await send(main.dp, bot, new_user_id, text="Turmush qurmagan")
    assert "shahar" in sent[-1].text.lower() or "tuman" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="Toshkent")
    assert "manzil" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="Chilonzor MFY, 12-uy")
    assert "sana" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="01.08.2026")
    assert "grafig" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="09:00-18:00")
    assert "Tungi smenada ishlay olasizmi?" in sent[-1].text

    sent = await send(main.dp, bot, new_user_id, text="🔄 Ba'zan ishlay olaman")
    assert "jamoaga yordam" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="✅ Ha, roziman")
    assert "topshiriq bersa" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="✅ Ha, roziman")
    assert "muddat" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="1–2 yil")
    assert "kompaniyada ishlamoqchisiz" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="Yaxshi jamoa bor")
    assert "tajriba" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="➖ O'tkazib yuborish")
    assert "tavsif" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="Yo'q")
    assert "qo'ng'iroq" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="Kontakt Bir")
    assert "rasm" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, photo_file_id="photo_abc")
    assert "izoh" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="➖ O'tkazib yuborish")
    assert "Anketangizni tekshiring" in sent[-1].text
    assert "Toshkent" in sent[-1].text
    assert "Chilonzor MFY" in sent[-1].text

    sent = await send(main.dp, bot, new_user_id, text="✅ Ma'lumotlar to'g'ri")
    applicant_messages = [m for m in sent if getattr(m, "chat_id", None) == new_user_id]
    assert "qabul qilindi" in applicant_messages[-1].text.lower()

    founder_review = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_review) == 1
    assert "Familiyev Ism Ota" in founder_review[0].caption

    from employees import format_founder_card, get_profile

    profile = get_profile(new_user_id)
    assert profile["status"] == "submitted"
    assert profile["tuman"] == "Toshkent"
    assert profile["mahalla"] == "Chilonzor MFY, 12-uy"

    card = format_founder_card(new_user_id)
    assert "Toshkent, Chilonzor MFY, 12-uy" in card
    assert "Familiyev Ism Ota" in card

    founder_sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"approve:{new_user_id}", target_chat_id=FOUNDER_ID
    )
    from roles import get_role

    assert get_role(new_user_id) == "nazoratchi"
    profile = get_profile(new_user_id)
    assert profile["status"] == "approved"

    sent = await send(main.dp, bot, new_user_id, text="/start")
    assert "💼 Lavozimingiz" in sent[-1].text


async def test_approve_sends_employee_menu_without_requiring_start(bot_dp):
    main, bot = bot_dp
    user_id = 60010

    invite_sent = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token = invite_sent[0].text.split("start=")[1].split()[0]
    await _complete_onboarding(main, bot, user_id, token)

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"approve:{user_id}", target_chat_id=FOUNDER_ID
    )

    applicant_messages = [m for m in sent if getattr(m, "chat_id", None) == user_id]
    assert len(applicant_messages) == 1
    assert "/start" not in applicant_messages[0].text
    assert "💼 Lavozimingiz" in applicant_messages[0].text
    assert applicant_messages[0].reply_markup.keyboard


async def test_approve_does_not_send_menu_when_role_assignment_fails(bot_dp, monkeypatch):
    """Regressiya: agar ``roles.set_role`` DB darajasidagi race tufayli
    ``False`` qaytarsa (masalan single-slot rolga deyarli bir vaqtdagi
    ikkinchi urinish), nomzodga muvaffaqiyat xabari/menyu
    yuborilmasligi kerak — bu holatda Founder ogohlantiriladi.
    """
    import approval

    main, bot = bot_dp
    user_id = 60012

    invite_sent = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token = invite_sent[0].text.split("start=")[1].split()[0]
    await _complete_onboarding(main, bot, user_id, token)

    monkeypatch.setattr(approval.roles, "set_role", lambda *args, **kwargs: False)

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"approve:{user_id}", target_chat_id=FOUNDER_ID
    )

    applicant_messages = [m for m in sent if getattr(m, "chat_id", None) == user_id]
    assert applicant_messages == []

    from employees import get_profile

    assert get_profile(user_id)["status"] == "approved"


def test_build_menu_and_category_menu_are_persistent(bot_dp):
    main, bot = bot_dp

    from roles import set_role

    assert main.build_menu(FOUNDER_ID).is_persistent is True

    employee_id = 60011
    set_role(employee_id, "nazoratchi", set_by=FOUNDER_ID)
    assert main.build_menu(employee_id).is_persistent is True

    assert main.build_category_menu(["/expense"]).is_persistent is True


async def test_menu_buttons_still_work_for_founder(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="📦 Ombor")
    assert "Ombor" in sent[0].text

    sent = await send(main.dp, bot, FOUNDER_ID, text="⚙️ Sozlamalar")
    assert "Sozlamalar" in sent[0].text


async def test_menu_buttons_rejected_for_stranger(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, 999999, text="📦 Ombor")
    assert sent[0].text == main.STRANGER_TEXT


async def test_invite_branch_role_requires_branch(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/invite sotuvchi")
    assert "Foydalanish" in sent[0].text

    sent = await send(main.dp, bot, FOUNDER_ID, text="/invite sotuvchi Chilonzor filiali")
    assert "Taklif havolasi yaratildi" in sent[0].text
    assert "Chilonzor filiali" in sent[0].text


async def test_reject_flow(bot_dp):
    main, bot = bot_dp
    user_id = 60001

    invite_sent = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token = invite_sent[0].text.split("start=")[1].split()[0]
    await _complete_onboarding(main, bot, user_id, token)

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"reject:{user_id}", target_chat_id=FOUNDER_ID
    )
    applicant_messages = [m for m in sent if getattr(m, "chat_id", None) == user_id]
    assert "rad etildi" in applicant_messages[0].text.lower()

    from employees import get_profile
    from roles import get_role

    assert get_profile(user_id)["status"] == "rejected"
    assert get_role(user_id) is None


async def test_detail_callback_shows_motivation(bot_dp):
    main, bot = bot_dp
    user_id = 60002

    invite_sent = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token = invite_sent[0].text.split("start=")[1].split()[0]
    await _complete_onboarding(main, bot, user_id, token)

    sent = await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"detail:{user_id}", target_chat_id=FOUNDER_ID
    )
    assert "Yaxshi jamoa bor" in sent[0].text


async def test_non_founder_cannot_approve(bot_dp):
    main, bot = bot_dp
    user_id = 60003

    invite_sent = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token = invite_sent[0].text.split("start=")[1].split()[0]
    await _complete_onboarding(main, bot, user_id, token)

    await send_callback(main.dp, bot, user_id, data=f"approve:{user_id}", target_chat_id=user_id)

    from employees import get_profile

    assert get_profile(user_id)["status"] == "submitted"


async def test_rejected_applicant_can_be_reinvited_and_resubmit(bot_dp):
    """Regression: submit_profile ikkinchi marta chaqirilganda (masalan
    rad etilgan xodim qayta taklif qilinsa) FOREIGN KEY xatosi bermasligi
    kerak — emergency_contact_id eski kontaktga ishora qilib turgani
    uchun avval shu ustun bo'shatilishi kerak.
    """
    main, bot = bot_dp
    user_id = 60004

    first_invite = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token = first_invite[0].text.split("start=")[1].split()[0]
    await _complete_onboarding(main, bot, user_id, token)

    await send_callback(
        main.dp, bot, FOUNDER_ID, data=f"reject:{user_id}", target_chat_id=FOUNDER_ID
    )

    second_invite = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    token2 = second_invite[0].text.split("start=")[1].split()[0]

    await _complete_onboarding(main, bot, user_id, token2, familiya="Familiyev2")

    from employees import get_profile

    profile = get_profile(user_id)
    assert profile["status"] == "submitted"
    assert profile["familiya"] == "Familiyev2"
    assert len(profile["contacts"]) == 2


def _keyboard_texts(message) -> list[str]:
    return [btn.text for row in message.reply_markup.keyboard for btn in row]


async def test_onboarding_new_agreements_and_night_shift(bot_dp):
    """Manzil misoli neytral, tungi smena savoli ham preset, ham qo'lda
    kiritilgan grafikdan keyin chiqadi, ikki kelishuv 1/0 sifatida
    saqlanadi va "Yo'q" javobi anketani avtomatik rad etmaydi."""
    main, bot = bot_dp

    import invites
    from employees import get_profile

    async def _fill_until_address_prompt(user_id: int, token: str):
        await send(main.dp, bot, user_id, text=f"/start {token}")
        for answer in (
            "Familiyev", "Ism", "Ota", "01.05.1995", "Erkak", "+998901234567",
            "Kontakt Bir", "+998901111111", "Aka",
            "Kontakt Ikki", "+998902222222", "Opa",
            "Turmush qurmagan",
        ):
            await send(main.dp, bot, user_id, text=answer)
        return await send(main.dp, bot, user_id, text="Toshkent")

    async def _finish_after_planned_duration(user_id: int):
        await send(main.dp, bot, user_id, text="1–2 yil")
        await send(main.dp, bot, user_id, text="Yaxshi jamoa bor")
        await send(main.dp, bot, user_id, text="➖ O'tkazib yuborish")
        await send(main.dp, bot, user_id, text="Yo'q")
        await send(main.dp, bot, user_id, text="Kontakt Bir")
        await send(main.dp, bot, user_id, photo_file_id="photo_abc")
        return await send(main.dp, bot, user_id, text="➖ O'tkazib yuborish")

    # --- 1) Qo'lda kiritiladigan grafik yo'li ---
    manual_id = 60050
    manual_token = invites.create_invite("kassir", "Filial-1", FOUNDER_ID)

    sent = await _fill_until_address_prompt(manual_id, manual_token)
    address_prompt = sent[-1].text
    assert "Muhsiniy" not in address_prompt
    assert "74-uy" not in address_prompt
    assert "23-xonadon" not in address_prompt
    assert "Uy manzilingizni kiriting." in address_prompt
    assert "Alisher Navoiy ko‘chasi, 15-uy" in address_prompt

    await send(main.dp, bot, manual_id, text="Chilonzor MFY, 12-uy")
    sent = await send(main.dp, bot, manual_id, text="01.08.2026")
    assert sent[-1].text == "Asosiy (odatdagi) ish grafigingizni kiriting. Masalan: 09:00–18:00"

    sent = await send(main.dp, bot, manual_id, text="09:00-18:00")
    assert sent[-1].text == "Tungi smenada ishlay olasizmi?"
    assert _keyboard_texts(sent[-1]) == [
        "✅ Ha, doim ishlay olaman",
        "🔄 Ba'zan ishlay olaman",
        "❌ Yo'q, faqat kunduzgi smena",
    ]

    sent = await send(main.dp, bot, manual_id, text="❌ Yo'q, faqat kunduzgi smena")
    assert "bu mening ishim emas" in sent[-1].text
    assert _keyboard_texts(sent[-1]) == ["✅ Ha, roziman", "❌ Yo'q, rozimasman"]

    sent = await send(main.dp, bot, manual_id, text="❌ Yo'q, rozimasman")
    assert "sen menga xo'jayin emassan" in sent[-1].text
    assert _keyboard_texts(sent[-1]) == ["✅ Ha, roziman", "❌ Yo'q, rozimasman"]

    # "Yo'q" avtomatik rad qilmaydi — anketa keyingi savol bilan davom etadi.
    sent = await send(main.dp, bot, manual_id, text="❌ Yo'q, rozimasman")
    assert "muddat" in sent[-1].text.lower()

    sent = await _finish_after_planned_duration(manual_id)
    summary = sent[-1].text
    assert "🌙 Tungi smena: Yo'q, faqat kunduzgi smena" in summary
    assert "🤝 Jamoaga yordam: Yo'q" in summary
    assert "🧭 Rahbar/ustoz topshirig'i: Yo'q" in summary

    await send(main.dp, bot, manual_id, text="✅ Ma'lumotlar to'g'ri")
    profile = get_profile(manual_id)
    assert profile["status"] == "submitted"
    assert profile["night_shift_availability"] == "day_only"
    assert profile["teamwork_agreement"] == 0
    assert profile["authority_cooperation_agreement"] == 0

    # --- 2) Preset (invite'dagi) grafik yo'li ---
    preset_id = 60051
    preset_token = invites.create_invite(
        "sotuvchi", "Filial-1", FOUNDER_ID, work_schedule="10:00-19:00"
    )

    await _fill_until_address_prompt(preset_id, preset_token)
    await send(main.dp, bot, preset_id, text="Chilonzor MFY, 12-uy")

    sent = await send(main.dp, bot, preset_id, text="01.08.2026")
    assert sent[-1].text == "Tungi smenada ishlay olasizmi?"

    sent = await send(main.dp, bot, preset_id, text="✅ Ha, doim ishlay olaman")
    assert "bu mening ishim emas" in sent[-1].text

    sent = await send(main.dp, bot, preset_id, text="✅ Ha, roziman")
    assert "sen menga xo'jayin emassan" in sent[-1].text

    sent = await send(main.dp, bot, preset_id, text="✅ Ha, roziman")
    assert "muddat" in sent[-1].text.lower()

    sent = await _finish_after_planned_duration(preset_id)
    summary = sent[-1].text
    assert "🕒 Ish grafigi: 10:00-19:00" in summary
    assert "🌙 Tungi smena: Ha, doim ishlay olaman" in summary
    assert "🤝 Jamoaga yordam: Ha" in summary
    assert "🧭 Rahbar/ustoz topshirig'i: Ha" in summary

    await send(main.dp, bot, preset_id, text="✅ Ma'lumotlar to'g'ri")
    profile = get_profile(preset_id)
    assert profile["status"] == "submitted"
    assert profile["work_schedule"] == "10:00-19:00"
    assert profile["night_shift_availability"] == "always"
    assert profile["teamwork_agreement"] == 1
    assert profile["authority_cooperation_agreement"] == 1
