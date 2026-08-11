import pytest

from config import FOUNDER_ID
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio


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
    assert "Asoschi" in sent[0].text


async def test_stranger_start_is_rejected(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, 999999, text="/start")

    assert len(sent) == 1
    assert sent[0].text == main.STRANGER_TEXT


async def test_stranger_founder_only_commands_are_silently_ignored(bot_dp):
    main, bot = bot_dp

    for command in ("/invite", "/listusers", "/setrule x 1", "/processmonth 1 2026-01 1 1 1"):
        sent = await send(main.dp, bot, 999999, text=command)
        assert sent == [], f"{command} begona foydalanuvchiga javob berdi"


async def test_invite_and_setrole_flow(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/invite nazoratchi")
    assert len(sent) == 1
    assert "Taklif havolasi yaratildi" in sent[0].text
    assert "https://t.me/test_bot?start=" in sent[0].text

    token = sent[0].text.split("start=")[1].split()[0]

    sent = await send(main.dp, bot, 555, text=f"/start {token}")
    assert any("Ismingiz" in t or "F.I.Sh" in t or "Familiya" in t for t in texts(sent)), texts(sent)


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
    assert sent == []
    assert get_role(222) is None

    sent = await send(main.dp, bot, 111, text="/invite nazoratchi")
    assert sent == []

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
    assert sent == []

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
    assert "mahalla" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="Chilonzor MFY, 12-uy")
    assert "sana" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="01.08.2026")
    assert "grafig" in sent[-1].text.lower()

    sent = await send(main.dp, bot, new_user_id, text="09:00-18:00")
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
    assert "Rolingiz" in sent[-1].text


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
