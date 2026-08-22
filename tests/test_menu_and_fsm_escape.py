import pytest

from config import FOUNDER_ID
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _set_role(user_id: int, role_key: str) -> None:
    from roles import set_role

    set_role(user_id, role_key, set_by=FOUNDER_ID)


# ------------------------------------------------ FSM-holatdan qochish --


async def test_stale_penalty_state_does_not_swallow_a_different_command(bot_dp):
    """Regression: nazoratchi jarima uchun nizom raqamini kutayotgan
    holatda (``PenaltyStates.waiting_rule``) boshqa buyruq (``/kunniyop``)
    yuborsa, u eski holat tomonidan "nizom raqami" deb noto'g'ri
    talqin qilinmasdan, o'zining haqiqiy buyrug'i sifatida ishlashi kerak.
    """
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)

    sent = await send(main.dp, bot, 1, text="/kunniyop")
    assert any("yopildi" in (m.text or "") for m in sent), [m.text for m in sent]

    from services import discipline

    assert discipline.get_salary(111)["bonus_bank"] == 0  # jarima qo'llanmadi


async def test_stale_penalty_state_does_not_swallow_start(bot_dp):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)

    sent = await send(main.dp, bot, 1, text="/start")
    assert any("Rolingiz" in (m.text or "") or "Asoschi" in (m.text or "") for m in sent)


async def test_cancel_button_clears_stale_state(bot_dp):
    main, bot = bot_dp
    _set_role(1, "nazoratchi")
    _set_role(111, "kassir")

    await send_callback(main.dp, bot, 1, data="bos:pen:111:10", target_chat_id=1)

    sent = await send(main.dp, bot, 1, text="❌ Bekor qilish")
    assert "bekor qilindi" in sent[0].text.lower()

    # Holat tozalangani uchun "3-nizom" endi hech qanday jarima
    # oqimiga tegishli emas — oddiy matn sifatida e'tiborsiz qolishi kerak.
    sent = await send(main.dp, bot, 1, text="3-nizom")
    assert sent == []

    from services import discipline

    assert discipline.get_salary(111)["bonus_bank"] == 0


# ------------------------------------------------------------- menyu --


async def test_start_shows_role_specific_category_for_kassir(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/start")
    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}

    assert "💰 Kassa" in buttons
    assert "⭐ Mening natijalarim" in buttons
    assert "👑 Asoschi" not in buttons


async def test_start_shows_founder_category_for_founder(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")
    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}

    assert buttons == {
        "👤 Xodim qo'shish", "👥 Xodimlar", "🏪 Do'konlar", "💰 Smenalarni ko'rish", "⚙️ Sozlamalar",
    }


async def test_category_button_lists_commands_and_back(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="💰 Kassa")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]

    assert "🟢 Smenani boshlash" in buttons
    assert "🔴 Smenani topshirish" in buttons
    assert "💸 Xarajat kiritish" in buttons
    assert "🔙 Orqaga" in buttons


async def test_kassir_menu_buttons_are_paired_two_per_row(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="💰 Kassa")
    rows = sent[0].reply_markup.keyboard

    assert [btn.text for btn in rows[0]] == ["🟢 Smenani boshlash", "🔴 Smenani topshirish"]
    assert [btn.text for btn in rows[1]] == ["💸 Xarajat kiritish"]
    assert [btn.text for btn in rows[2]] == ["🔙 Orqaga"]


async def test_kassir_friendly_button_still_triggers_real_command(bot_dp):
    """Yangi sodda tugma matni ("🟢 Smenani boshlash") bosilganda ham
    asl ``/openshift`` handleri ishga tushishi kerak — eski komanda
    orqada o'zgarishsiz ishlab turadi, faqat foydalanuvchiga ko'rinmaydi.
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="🟢 Smenani boshlash")

    assert sent != []


async def test_kassir_friendly_button_escapes_stale_expense_state(bot_dp):
    """Regressiya: kassirning yangi sodda tugma matni ("/" bilan
    boshlanmaydi) ``_ClearStaleStateMiddleware`` tomonidan "qochish"
    sifatida tanilmasa, ``/expense`` kategoriya kutayotgan holatda
    qolib ketgan kassir "🟢 Smenani boshlash" bossa, bu matn noto'g'ri
    kategoriya nomi sifatida yutib olinardi (generic/fallback javob) —
    haqiqiy ``/openshift`` handleriga umuman yetib bormasdi.
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    await send(main.dp, bot, 111, text="/openshift")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="/expense")  # ExpenseStates.category holatida qoladi

    sent = await send(main.dp, bot, 111, text="🟢 Smenani boshlash")

    assert "tugmalardan birini tanlang" not in sent[0].text
    assert "allaqachon ochilgan" in sent[0].text


async def test_top_level_menu_button_escapes_stale_expense_state(bot_dp):
    """Regressiya: asosiy menyu/bo'lim tugmalari ("💰 Kassa" va h.k.) ham
    "/" bilan boshlanmaydi — kassir ``/expense`` kategoriya kutayotgan
    holatda qolib ketib, "💰 Kassa" tugmasini bossa, bu ham noto'g'ri
    kategoriya nomi sifatida yutib olinmasligi, aksincha bo'lim
    menyusini ochishi kerak (qarang ``_TOP_LEVEL_NAV_TEXTS``).
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    await send(main.dp, bot, 111, text="/openshift")
    await send(main.dp, bot, 111, text="0")
    await send(main.dp, bot, 111, text="/expense")  # ExpenseStates.category holatida qoladi

    sent = await send(main.dp, bot, 111, text="💰 Kassa")

    assert "tugmalardan birini tanlang" not in sent[0].text
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "🟢 Smenani boshlash" in buttons


# --------------------------------- regressiya: tugma matnida izoh yubormasin --
# Bug: bo'lim tugmasi to'liq "/invite — Yangi xodimga taklif havolasi" matnini
# yuborardi — Command filtri buni "/invite" + argument ("— Yangi ...") deb
# talqin qilib, handler "—"ni rol kaliti sifatida qabul qilib
# "Noto'g'ri rol kaliti: —" xatosini chiqarardi.


def test_bare_command_strips_description_from_every_menu_entry():
    import main

    for _category, label, _action in main._MENU_ENTRIES:
        bare = main._bare_command(label)
        assert bare.startswith("/")
        assert " " not in bare
        assert "—" not in bare

    for label in main._SHARED_COMMANDS:
        bare = main._bare_command(label)
        assert bare.startswith("/")
        assert " " not in bare
        assert "—" not in bare


async def test_category_menu_buttons_contain_no_description_text(bot_dp):
    """Har bir bo'lim tugmasi FAQAT toza buyruq (yoki kassir uchun sodda
    yorliq) bo'lishi kerak — izohli qism ("— ...") tugma matniga umuman
    kirmasin.
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="💰 Kassa")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]

    assert "🟢 Smenani boshlash" in buttons
    assert "🔴 Smenani topshirish" in buttons
    assert "💸 Xarajat kiritish" in buttons
    assert not any("—" in b for b in buttons)


async def test_shared_category_buttons_contain_no_description_text(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="⭐ Mening natijalarim")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]

    assert "/mystars" in buttons
    assert not any("—" in b for b in buttons)


async def test_founder_category_buttons_contain_no_description_text(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="👑 Asoschi")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]

    assert "/invite" in buttons
    assert "/setrole" in buttons
    assert "/removeuser" in buttons
    assert "/listusers" in buttons
    assert not any("—" in b for b in buttons)


async def test_invite_button_press_does_not_report_invalid_role_key(bot_dp):
    """Regressiya: tugma bosilganda ``/invite`` argumentsiz kelishi kerak
    (foydalanish yo'riqnomasi ko'rsatiladi), "Noto'g'ri rol kaliti: —"
    emas.
    """
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="👑 Asoschi")
    sent = await send(main.dp, bot, FOUNDER_ID, text="/invite")

    assert "Noto'g'ri rol kaliti" not in sent[0].text
    assert "Foydalanish" in sent[0].text


async def test_setrole_button_press_does_not_leak_dash_as_argument(bot_dp):
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="👑 Asoschi")
    sent = await send(main.dp, bot, FOUNDER_ID, text="/setrole")

    assert "Noto'g'ri rol kaliti" not in sent[0].text
    assert "Foydalanish" in sent[0].text


@pytest.mark.parametrize(
    "role_key,category_label",
    [
        ("nazoratchi", "🧑‍💼 Nazoratchi"),
        ("kassir", "💰 Kassa"),
        ("savdo_boshligi", "📦 Ombor"),
        ("haydovchi", "🚚 Haydovchi"),
        ("taminotchi", "🛒 Ta'minotchi"),
        ("moliyachi", "💵 Moliyachi"),
    ],
)
async def test_every_role_category_buttons_are_description_free(bot_dp, role_key, category_label):
    main, bot = bot_dp
    _set_role(555, role_key)

    sent = await send(main.dp, bot, 555, text=category_label)
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]

    assert len(buttons) > 1  # kamida bitta buyruq + "Orqaga"
    assert not any("—" in b for b in buttons)
    assert all(
        b == "🔙 Orqaga" or b.startswith("/") or b in main._KASSIR_BUTTON_LABELS.values()
        for b in buttons
    )


# ------------------------- eski (Telegram'da keshlangan) izohli tugma --
# Foydalanuvchi qurilmasida oldingi bot versiyasi yuborgan izohli tugma
# ("/invite — Yangi xodimga taklif havolasi") hali ham saqlanib qolgan
# bo'lishi mumkin — /start bilan yangi klaviatura ko'rsatilmaguncha,
# bosilsa aynan shu to'liq matn xabar sifatida yuboriladi. Backend buni
# ham xavfsiz qabul qilishi kerak (qarang ``_NormalizeStaleMenuButtonMiddleware``).


def test_stale_label_map_covers_every_menu_entry_and_maps_to_bare_command():
    import main

    for _category, label, _action in main._MENU_ENTRIES:
        assert label in main._STALE_LABEL_TO_COMMAND
        assert main._STALE_LABEL_TO_COMMAND[label] == main._bare_command(label)

    for label in main._SHARED_COMMANDS:
        assert label in main._STALE_LABEL_TO_COMMAND
        assert main._STALE_LABEL_TO_COMMAND[label] == main._bare_command(label)


async def test_stale_cached_invite_button_text_is_normalized(bot_dp):
    """Aniq xabar qilingan bug: eski tugma to'liq
    "/invite — Yangi xodimga taklif havolasi" matnini yuboradi — bot
    buni "/invite" sifatida qabul qilishi kerak, "Noto'g'ri rol kaliti: —"
    emas.
    """
    main, bot = bot_dp

    sent = await send(
        main.dp, bot, FOUNDER_ID, text="/invite — Yangi xodimga taklif havolasi"
    )

    assert "Noto'g'ri rol kaliti" not in sent[0].text
    assert "Foydalanish" in sent[0].text


async def test_stale_cached_setrole_button_text_is_normalized(bot_dp):
    main, bot = bot_dp

    sent = await send(
        main.dp, bot, FOUNDER_ID, text="/setrole — Foydalanuvchiga rol berish"
    )

    assert "Noto'g'ri rol kaliti" not in sent[0].text
    assert "Foydalanish" in sent[0].text


async def test_stale_cached_removeuser_button_works_with_founder(bot_dp):
    main, bot = bot_dp
    _set_role(222, "sotuvchi")

    sent = await send(
        main.dp, bot, FOUNDER_ID, text="/removeuser — Foydalanuvchini ro'yxatdan o'chirish"
    )

    assert "Foydalanish: /removeuser" in sent[0].text


async def test_stale_cached_shared_command_button_is_normalized(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/mystars — Mening yulduzlarim")

    assert "Joriy yulduzlar" in sent[0].text


async def test_stale_button_normalization_does_not_touch_real_user_arguments(bot_dp):
    """Foydalanuvchi qo'lda yozgan haqiqiy argumentlar o'zgarishsiz
    qolishi kerak — bu matnlar ``_STALE_LABEL_TO_COMMAND``da yo'q.
    """
    main, bot = bot_dp
    from roles import get_role

    sent = await send(main.dp, bot, FOUNDER_ID, text="/invite sotuvchi")
    assert "Foydalanish: /invite" in sent[0].text  # filial talab qilinadi, xato emas

    sent = await send(main.dp, bot, FOUNDER_ID, text="/removeuser 222")
    assert "topilmadi" in sent[0].text  # 222 ro'yxatda yo'q, lekin argument to'g'ri o'qildi

    sent = await send(main.dp, bot, FOUNDER_ID, text="/setrole 333 sotuvchi")
    assert "rnatildi" in sent[0].text.lower()
    assert get_role(333) == "sotuvchi"


async def test_start_after_stale_button_shows_fresh_description_free_menu(bot_dp):
    """Eski keshlangan tugma matni bilan urinishdan keyin /start yangi
    (toza) klaviaturani ko'rsatishi kerak — talab #6.
    """
    main, bot = bot_dp

    await send(main.dp, bot, FOUNDER_ID, text="/invite — Yangi xodimga taklif havolasi")
    sent = await send(main.dp, bot, FOUNDER_ID, text="/start")

    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}
    assert "👤 Xodim qo'shish" in buttons
    assert not any("—" in b for b in buttons)


async def test_category_command_button_triggers_real_command(bot_dp):
    """Bo'lim ichidagi tugma matni haqiqiy buyruq bilan boshlanadi va
    bosilganda o'zining mavjud handleri ishga tushishi kerak (yangi
    biznes mantiq emas, faqat navigatsiya).
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="/openshift 0")
    assert sent != []


async def test_back_button_returns_to_main_menu(bot_dp):
    main, bot = bot_dp
    _set_role(111, "kassir")

    await send(main.dp, bot, 111, text="💰 Kassa")
    sent = await send(main.dp, bot, 111, text="🔙 Orqaga")

    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}
    assert "💰 Kassa" in buttons
    assert "⭐ Mening natijalarim" in buttons


async def test_sotuvchi_menu_has_no_role_category_button(bot_dp):
    """``sotuvchi`` rolida ``ROLE_PERMISSIONS``da bironta amal yo'q —
    menyu markaziy permission-matrixdan shakllangani uchun uning uchun
    HECH QANDAY bo'lim tugmasi chiqmasligi kerak (faqat AI/umumiy/
    sozlamalar), moliya/kassa/savdo tugmalari umuman ko'rinmaydi.
    """
    main, bot = bot_dp
    _set_role(222, "sotuvchi")

    sent = await send(main.dp, bot, 222, text="/start")
    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}

    role_category_buttons = set(main._CATEGORY_LABELS.values())
    assert buttons & role_category_buttons == set()
    assert "⭐ Mening natijalarim" in buttons
    assert "🤖 AI Tahlil" in buttons


async def test_stale_category_button_after_role_change_is_rejected(bot_dp):
    """Foydalanuvchi "💰 Kassa" bo'limini ko'rgandan keyin roli
    o'zgartirilsa (endi kassir emas), mijozda keshlangan eski tugma
    matnini qayta yuborsa ham backend uni endi bermasligi kerak — bo'sh
    bo'lim o'rniga asosiy menyuga xushmuomalalik bilan qaytariladi.
    """
    main, bot = bot_dp
    _set_role(111, "kassir")

    sent = await send(main.dp, bot, 111, text="💰 Kassa")
    buttons = [btn.text for row in sent[0].reply_markup.keyboard for btn in row]
    assert "🟢 Smenani boshlash" in buttons

    _set_role(111, "sotuvchi")

    sent = await send(main.dp, bot, 111, text="💰 Kassa")
    assert "Asosiy menyu" in sent[0].text
    buttons = {btn.text for row in sent[0].reply_markup.keyboard for btn in row}
    assert "💰 Kassa" not in buttons
