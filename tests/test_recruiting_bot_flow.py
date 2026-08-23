"""Fokus HR — nomzod suhbati end-to-end (Telegram simulyatsiyasi
orqali), Founder karta/qaror, RBAC izolyatsiyasi, bekor qilish/davom
ettirish, moslik filtri (fit) va real Telegram sinovida topilgan
kamchiliklarning tuzatilganini tekshiruvchi regression testlar."""

from datetime import date

import pytest
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import Contact, Voice

from config import FOUNDER_ID
from repositories import recruiting as recruiting_repo
from services import recruiting_voice
from tests.bot_harness import make_message, send, send_callback

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


CANDIDATE_ID = 900001
OTHER_CANDIDATE_ID = 900002


def _last_text(sent) -> str:
    for method in reversed(sent):
        t = getattr(method, "text", None) or getattr(method, "caption", None)
        if t:
            return t
    return ""


def _texts_to(sent, chat_id: int) -> list[str]:
    result = []
    for method in sent:
        if getattr(method, "chat_id", None) != chat_id:
            continue
        t = getattr(method, "text", None) or getattr(method, "caption", None)
        if t:
            result.append(t)
    return result


def _kassir_id() -> int:
    return recruiting_repo.get_vacancy_by_key("kassir")["id"]


async def _start_and_consent(main, bot, candidate_id: int) -> None:
    await send(main.dp, bot, candidate_id, text="/apply")
    await send_callback(main.dp, bot, candidate_id, "rec_consent:yes", target_chat_id=candidate_id)


async def _choose_kassir(main, bot, candidate_id: int) -> None:
    await send_callback(main.dp, bot, candidate_id, f"rec_vacancy:{_kassir_id()}", target_chat_id=candidate_id)


async def _answer_basics(main, bot, candidate_id: int, birth_year: str = "2000") -> None:
    await send(main.dp, bot, candidate_id, text="Ali Valiyev")  # full_name
    await send(main.dp, bot, candidate_id, text=birth_year)  # birth_year
    await send(main.dp, bot, candidate_id, text="+998901234567")  # phone
    await send(main.dp, bot, candidate_id, text="Toshkent, Chilonzor")  # residence_area
    await send(main.dp, bot, candidate_id, text="Chilonzor filiali")  # preferred_branch
    await send(main.dp, bot, candidate_id, text="Bir hafta ichida")  # start_date


async def _answer_fit_filter(
    main, bot, candidate_id: int, shift: str = "kunduzgi", holiday: str = "yes", commute: str = "no", accommodation: str = "no"
):
    await send_callback(main.dp, bot, candidate_id, f"rec_choice:shift_preference:{shift}", target_chat_id=candidate_id)
    await send(main.dp, bot, candidate_id, text="yo'q")  # unavailable_days
    await send_callback(main.dp, bot, candidate_id, f"rec_choice:holiday_available:{holiday}", target_chat_id=candidate_id)
    await send(main.dp, bot, candidate_id, text="4 million so'm")  # expected_salary
    await send_callback(main.dp, bot, candidate_id, f"rec_choice:commute_issue:{commute}", target_chat_id=candidate_id)
    return await send_callback(
        main.dp, bot, candidate_id, f"rec_choice:accommodation_needed:{accommodation}", target_chat_id=candidate_id
    )


async def _answer_experience(main, bot, candidate_id: int) -> None:
    await send(main.dp, bot, candidate_id, text="ABC do'koni, sotuvchi")  # prev_employer
    await send(main.dp, bot, candidate_id, text="2 yil")  # experience_duration
    await send(main.dp, bot, candidate_id, text="Ish joyi uyimga yaqinroq kerak edi")  # leave_reason
    await send_callback(main.dp, bot, candidate_id, "rec_choice:pos_experience:yes", target_chat_id=candidate_id)
    await send(main.dp, bot, candidate_id, text="Qaytim berish va smena yopish tajribam bor")  # cash_handling
    await send_callback(main.dp, bot, candidate_id, "rec_choice:reference_check_consent:yes", target_chat_id=candidate_id)


async def _complete_intake(main, bot, candidate_id: int, **fit_kwargs) -> None:
    """Consent'dan tortib D bo'limi oxirigacha (E'dan oldin) — mos
    (fit) holatda, D bo'limi ham so'raladi."""
    await _start_and_consent(main, bot, candidate_id)
    await _choose_kassir(main, bot, candidate_id)
    await _answer_basics(main, bot, candidate_id)
    await _answer_fit_filter(main, bot, candidate_id, **fit_kwargs)
    await _answer_experience(main, bot, candidate_id)


_SAFE_KASSIR_ANSWERS = [
    "Darhol rahbarga aytib, hisobni tekshiraman",  # kamomad
    "Narxni tekshirib, xaridorga tushuntiraman",  # narx_farqi
    "Ishdan keyin qo'ng'iroq qilaman",  # telefon
    "Hech kimga bermayman, faqat o'zim ishlataman",  # login
    "Kassa egasi javobgar bo'lishi kerak deb o'ylayman",  # javobgarlik
    "Xotirjam tinglab, yechim topishga harakat qilaman",  # janjal
    "Darhol chetga olib, rahbarga xabar beraman",  # muddat
    "Oldindan albatta xabar beraman va kechikmaslikka harakat qilaman",  # umumiy_kech_qolish
]


async def _answer_role_questions_safely(main, bot, candidate_id: int) -> None:
    for answer in _SAFE_KASSIR_ANSWERS:
        await send(main.dp, bot, candidate_id, text=answer)


async def _answer_math_correctly(main, bot, candidate_id: int) -> int:
    application = recruiting_repo.get_in_progress_application(candidate_id)
    application_id = application["id"]
    await send_callback(
        main.dp, bot, candidate_id, f"rec_math:{application_id}:b", target_chat_id=candidate_id
    )
    return application_id


# --------------------------------------------------------------- to'liq oqim --


async def test_full_kassir_application_flow_sends_founder_card(bot_dp):
    main, bot = bot_dp

    await _complete_intake(main, bot, CANDIDATE_ID)
    await _answer_role_questions_safely(main, bot, CANDIDATE_ID)
    await _answer_math_correctly(main, bot, CANDIDATE_ID)

    sent = await send(main.dp, bot, CANDIDATE_ID, text="Mijozlarga xizmat qilishni yaxshi ko'raman")

    candidate_texts = _texts_to(sent, CANDIDATE_ID)
    assert any("rahmat" in t.lower() for t in candidate_texts)
    # Nomzod ballarni yoki ichki tahlilni ko'rmasligi kerak.
    assert not any("ball" in t.lower() for t in candidate_texts)
    assert not any("INTERVIEW_RECOMMENDED" in t for t in candidate_texts)

    founder_messages = [m for m in sent if isinstance(m, (SendMessage, SendPhoto)) and getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_messages) == 1
    founder_card_text = founder_messages[0].text
    assert "Nomzod kartasi" in founder_card_text
    assert "Ali Valiyev" in founder_card_text
    assert "AI/deterministik TAVSIYA" in founder_card_text
    assert "2000" in founder_card_text  # tug'ilgan yil ko'rsatiladi
    assert "ballga ta'sir qilmaydi" in founder_card_text


async def test_founder_receives_photo_when_candidate_uploads_one(bot_dp):
    """Regressiya: nomzod majburiy foto bosqichida haqiqiy rasm
    yuborsa, Founder shu fotoni (mavjud ``send_photo`` mexanizmi
    orqali, ``candidate_photo_file_id``) olishi kerak — karta matni/
    tugmalari o'zgarishsiz qoladi.
    """
    main, bot = bot_dp

    await _complete_intake(main, bot, CANDIDATE_ID)
    await _answer_role_questions_safely(main, bot, CANDIDATE_ID)
    await _answer_math_correctly(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Mijozlarga xizmat qilishni yaxshi ko'raman")
    sent = await send(main.dp, bot, CANDIDATE_ID, photo_file_id="candidate_photo_abc")

    founder_photos = [
        m for m in sent if isinstance(m, SendPhoto) and getattr(m, "chat_id", None) == FOUNDER_ID
    ]
    assert len(founder_photos) == 1
    assert founder_photos[0].photo == "candidate_photo_abc"

    founder_cards = [
        m for m in sent
        if isinstance(m, SendMessage) and getattr(m, "chat_id", None) == FOUNDER_ID and "Nomzod kartasi" in (m.text or "")
    ]
    assert len(founder_cards) == 1


async def test_founder_card_still_sent_when_photo_send_fails(bot_dp, monkeypatch):
    """Regressiya: agar Founderga foto yuborish muvaffaqiyatsiz bo'lsa
    (masalan vaqtinchalik Telegram xatosi), bu butun bildirishnomani —
    matnli nomzod kartasini — yo'qotib qo'ymasligi kerak (talab: "Foto
    bo'lmasa oqim yiqilmasin, matnli karta ishlayversin").
    """
    main, bot = bot_dp

    async def _raise(*args, **kwargs):
        raise RuntimeError("Simulyatsiya: foto yuborib bo'lmadi")

    monkeypatch.setattr(bot, "send_photo", _raise)

    await _complete_intake(main, bot, CANDIDATE_ID)
    await _answer_role_questions_safely(main, bot, CANDIDATE_ID)
    await _answer_math_correctly(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Mijozlarga xizmat qilishni yaxshi ko'raman")
    sent = await send(main.dp, bot, CANDIDATE_ID, photo_file_id="candidate_photo_abc")

    founder_cards = [
        m for m in sent
        if isinstance(m, SendMessage) and getattr(m, "chat_id", None) == FOUNDER_ID and "Nomzod kartasi" in (m.text or "")
    ]
    assert len(founder_cards) == 1


async def test_candidate_does_not_see_internal_menus_during_application(bot_dp):
    main, bot = bot_dp

    sent = await send(main.dp, bot, CANDIDATE_ID, text="/apply")
    text = _last_text(sent)
    assert "Sozlamalar" not in text
    assert "AI Tahlil" not in text


async def test_no_data_collected_before_consent(bot_dp):
    main, bot = bot_dp

    await send(main.dp, bot, CANDIDATE_ID, text="/apply")
    # Rozilik berilmasdan turib bo'sh matn yuborilsa, ariza yaratilmaydi.
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")

    assert recruiting_repo.get_in_progress_application(CANDIDATE_ID) is None


async def test_no_active_vacancy_message(bot_dp):
    main, bot = bot_dp

    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    sotuvchi = recruiting_repo.get_vacancy_by_key("sotuvchi")
    recruiting_repo.set_vacancy_active(kassir["id"], False)
    recruiting_repo.set_vacancy_active(sotuvchi["id"], False)

    sent = await send(main.dp, bot, CANDIDATE_ID, text="/apply")
    assert "faol vakansiya mavjud emas" in _last_text(sent).lower()

    recruiting_repo.set_vacancy_active(kassir["id"], True)
    recruiting_repo.set_vacancy_active(sotuvchi["id"], True)


# -------------------------------------------------------- bekor qilish/davom --


async def test_cancel_marks_application_cancelled(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application is not None

    sent = await send(main.dp, bot, CANDIDATE_ID, text="🚫 Arizani bekor qilish")
    assert "bekor qilindi" in _last_text(sent).lower()
    assert recruiting_repo.get_in_progress_application(CANDIDATE_ID) is None

    cancelled = recruiting_repo.get_application(application["id"])
    assert cancelled["status"] == "cancelled"


async def test_resume_continues_from_saved_step(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")
    await send(main.dp, bot, CANDIDATE_ID, text="2000")  # birth_year

    # "Restart" simulyatsiyasi: xuddi shu foydalanuvchi /apply'ni qayta
    # bosadi — DB'dagi tugallanmagan ariza asosida davom etishi kerak,
    # yangi ariza yaratmasligi kerak.
    application_before = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    sent = await send(main.dp, bot, CANDIDATE_ID, text="/apply")

    assert any("saqlangan" in t.lower() for t in _texts_to(sent, CANDIDATE_ID))
    application_after = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application_before["id"] == application_after["id"]

    # Davom etib, telefon savoliga to'g'ri javob berish kerak (chunki
    # keyingi qadam "phone" bo'lishi kerak, "full_name" emas).
    await send(main.dp, bot, CANDIDATE_ID, text="+998901234567")
    updated = recruiting_repo.get_application(application_after["id"])
    assert updated["phone"] == "+998901234567"


# ------------------------------------------------------------ moslashuvchan --


async def test_risky_answer_triggers_follow_up_and_records_it(bot_dp):
    main, bot = bot_dp

    await _complete_intake(main, bot, CANDIDATE_ID)

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)

    # kassir_kamomad, kassir_narx_farqi, kassir_telefon — xavfsiz javoblar.
    await send(main.dp, bot, CANDIDATE_ID, text="Darhol rahbarga aytaman")
    await send(main.dp, bot, CANDIDATE_ID, text="Narxni tekshiraman")
    await send(main.dp, bot, CANDIDATE_ID, text="Keyinroq qo'ng'iroq qilaman")

    # kassir_login — xavfli javob, follow-up kutiladi.
    sent = await send(main.dp, bot, CANDIDATE_ID, text="Ishongan eski xodimga kassamni beraman")
    follow_up_text = _last_text(sent)
    assert "javobgar" in follow_up_text.lower() or "aniq" in follow_up_text.lower()

    await send(main.dp, bot, CANDIDATE_ID, text="Yo'q, albatta hech kimga bermayman")

    answers = recruiting_repo.get_answers(application["id"])
    follow_up_answers = [a for a in answers if a["is_follow_up"]]
    assert len(follow_up_answers) == 1


async def test_max_two_follow_ups_per_answer_then_moves_on(bot_dp):
    """Real sinovdan keyingi talab: follow-up cheklovi BUTUN suhbatga
    emas, BITTA javobga nisbatan (E bo'limidagi birinchi savolda ham
    ko'p marta bo'lishi mumkin, chunki hisoblagich har yangi savolda
    reset bo'ladi)."""
    main, bot = bot_dp

    await _complete_intake(main, bot, CANDIDATE_ID)
    risky = "Bilmayman, hech narsa qilmayman"

    # kassir_kamomad savoliga uchta marta noaniq javob — 2 tadan ortiq
    # aniqlashtirish so'ralmasligi va oxir-oqibat keyingi savolga
    # o'tishi kerak.
    for _ in range(3):
        await send(main.dp, bot, CANDIDATE_ID, text=risky)

    # Endi navbatdagi savol (kassir_narx_farqi)da bo'lishi kerak.
    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    answers = recruiting_repo.get_answers(application["id"])
    kamomad_answers = [a for a in answers if a["question_key"] == "kassir_kamomad"]
    # Asl javob + eng ko'pi bilan 2 ta follow-up javobi.
    assert len(kamomad_answers) <= 3


# ------------------------------------------------------------- moslik filtri --


async def test_underage_candidate_ends_early_with_neutral_message_no_situational_questions(bot_dp):
    """C bo'limi tugagach yosh mos kelmasa, D/E BUTUNLAY so'ralmaydi —
    suhbat neytral yakunlanadi, nomzod "yomon" deb aytilmaydi."""
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    too_young_birth_year = str(date.today().year - 14)
    await _answer_basics(main, bot, CANDIDATE_ID, birth_year=too_young_birth_year)

    application_before = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    sent = await _answer_fit_filter(main, bot, CANDIDATE_ID)

    candidate_texts = _texts_to(sent, CANDIDATE_ID)
    assert any("rahmat" in t.lower() for t in candidate_texts)
    assert not any("yomon" in t.lower() for t in candidate_texts)
    # D bo'limi (masalan "oldingi ish joyingiz") hech qachon so'ralmadi.
    assert not any("oldingi ish joyingiz" in t.lower() for t in candidate_texts)

    assert recruiting_repo.get_in_progress_application(CANDIDATE_ID) is None  # ariza yakunlangan

    submitted = recruiting_repo.get_application(application_before["id"])
    assert submitted["fit_result"] == "mismatch"
    assert submitted["status"] == "awaiting_review"

    assessment = recruiting_repo.get_assessment(application_before["id"])
    assert assessment["overall_result"] == "REQUIREMENT_MISMATCH"


async def test_fit_mismatch_sets_result_and_founder_still_gets_a_card(bot_dp):
    main, bot = bot_dp

    kassir_id = _kassir_id()
    recruiting_repo.set_vacancy_requirements(kassir_id, required_shift="kechki", requires_weekends=False)
    try:
        await _start_and_consent(main, bot, CANDIDATE_ID)
        await _choose_kassir(main, bot, CANDIDATE_ID)
        await _answer_basics(main, bot, CANDIDATE_ID)
        sent = await _answer_fit_filter(main, bot, CANDIDATE_ID, shift="kunduzgi")  # vakansiya "kechki" talab qiladi

        candidate_texts = _texts_to(sent, CANDIDATE_ID)
        assert any("rahmat" in t.lower() for t in candidate_texts)

        founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
        assert len(founder_messages) == 1
        assert "Mos emas" in founder_messages[0].text

        application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
        assert application is None
    finally:
        recruiting_repo.set_vacancy_requirements(kassir_id, required_shift=None, requires_weekends=False)


async def test_fit_match_continues_to_experience_section(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _answer_basics(main, bot, CANDIDATE_ID)
    sent = await _answer_fit_filter(main, bot, CANDIDATE_ID)

    # Standart vakansiyada hech qanday qat'iy talab yo'q — suhbat D
    # bo'limiga (tajriba) davom etishi kerak, "Rahmat" bilan yakunlanmaydi.
    text = _last_text(sent)
    assert "oldingi ish joyingiz" in text.lower()

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application is not None
    assert application["fit_result"] == "fit"


async def test_accommodation_needed_asks_followup_text(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _answer_basics(main, bot, CANDIDATE_ID)
    sent = await _answer_fit_filter(main, bot, CANDIDATE_ID, accommodation="yes")

    assert "qulaylik" in _last_text(sent).lower()

    await send(main.dp, bot, CANDIDATE_ID, text="O'tirib ishlash imkoniyati bo'lsa yaxshi bo'lardi")
    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["accommodation_text"] == "O'tirib ishlash imkoniyati bo'lsa yaxshi bo'lardi"


# ------------------------------------------------------------------- ovoz --


async def test_voice_too_long_is_rejected_and_asks_for_shorter(bot_dp, monkeypatch):
    main, bot = bot_dp

    await _complete_intake(main, bot, CANDIDATE_ID)
    await _answer_role_questions_safely(main, bot, CANDIDATE_ID)
    await _answer_math_correctly(main, bot, CANDIDATE_ID)

    called = False

    async def _fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        return "bu chaqirilmasligi kerak"

    monkeypatch.setattr(recruiting_voice, "transcribe_voice", _fail_if_called)

    message = make_message(CANDIDATE_ID, text=None)
    message = message.model_copy(
        update={"voice": Voice(file_id="v1", file_unique_id="vu1", duration=90)}
    )
    from aiogram.types import Update

    bot.sent = []
    await main.dp.feed_update(bot, Update(update_id=1, message=message))

    assert called is False
    assert "60" in _last_text(bot.sent) or "soniya" in _last_text(bot.sent).lower()


async def test_voice_transcription_unavailable_falls_back_to_text_request(bot_dp, monkeypatch):
    main, bot = bot_dp

    await _complete_intake(main, bot, CANDIDATE_ID)
    await _answer_role_questions_safely(main, bot, CANDIDATE_ID)
    await _answer_math_correctly(main, bot, CANDIDATE_ID)

    async def _return_none(*args, **kwargs):
        return None

    monkeypatch.setattr(recruiting_voice, "transcribe_voice", _return_none)

    message = make_message(CANDIDATE_ID, text=None)
    message = message.model_copy(
        update={"voice": Voice(file_id="v1", file_unique_id="vu1", duration=10)}
    )
    from aiogram.types import Update

    bot.sent = []
    await main.dp.feed_update(bot, Update(update_id=1, message=message))

    assert "matn" in _last_text(bot.sent).lower()
    # Ariza hali yakunlanmagan — hali motivation bosqichida.
    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application is not None
    assert application["current_step"] != "submitted"


async def test_voice_answer_uses_transcribed_text_when_available(bot_dp, monkeypatch):
    main, bot = bot_dp

    await _complete_intake(main, bot, CANDIDATE_ID)
    await _answer_role_questions_safely(main, bot, CANDIDATE_ID)
    application_id = await _answer_math_correctly(main, bot, CANDIDATE_ID)

    async def _fake_transcribe(*args, **kwargs):
        return "Chunki Saturn jamoasi juda yaxshi jamoa deb eshitganman"

    monkeypatch.setattr(recruiting_voice, "transcribe_voice", _fake_transcribe)

    message = make_message(CANDIDATE_ID, text=None)
    message = message.model_copy(
        update={"voice": Voice(file_id="v1", file_unique_id="vu1", duration=10)}
    )
    from aiogram.types import Update

    bot.sent = []
    await main.dp.feed_update(bot, Update(update_id=1, message=message))

    application = recruiting_repo.get_application(application_id)
    assert application["motivation_text"] == "Chunki Saturn jamoasi juda yaxshi jamoa deb eshitganman"

    answers = recruiting_repo.get_answers(application_id)
    motivation_answer = next(a for a in answers if a["question_key"] == "motivation")
    assert motivation_answer["answer_source"] == "voice"


# ------------------------------------------------------------------ telefon --


async def test_phone_accepts_shared_contact(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")
    await send(main.dp, bot, CANDIDATE_ID, text="2000")  # birth_year

    message = make_message(CANDIDATE_ID, text=None)
    message = message.model_copy(
        update={"contact": Contact(phone_number="+998901112233", first_name="Ali")}
    )
    from aiogram.types import Update

    bot.sent = []
    await main.dp.feed_update(bot, Update(update_id=1, message=message))

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["phone"] == "+998901112233"


async def test_invalid_birth_year_text_is_rejected(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")

    sent = await send(main.dp, bot, CANDIDATE_ID, text="qwerty")
    assert "tushunmadim" in _last_text(sent).lower()

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["birth_year"] is None


async def test_invalid_phone_text_is_rejected(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")
    await send(main.dp, bot, CANDIDATE_ID, text="2000")  # birth_year

    sent = await send(main.dp, bot, CANDIDATE_ID, text="qwerty")
    assert "noto'g'ri" in _last_text(sent).lower()

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["phone"] is None


# ------------------------------------------------------- AI ishlamasa ham --


async def test_application_completes_even_when_ai_client_is_unavailable(bot_dp, monkeypatch):
    """AI (follow-up/xulosa) ishlamasa ham suhbat hech qachon
    to'xtamasligi kerak — deterministik zaxiraga o'tadi."""
    main, bot = bot_dp

    async def _raise(*args, **kwargs):
        raise RuntimeError("OpenAI mavjud emas (simulyatsiya)")

    monkeypatch.setattr(main.openai_client.responses, "create", _raise)

    await _complete_intake(main, bot, CANDIDATE_ID)
    await _answer_role_questions_safely(main, bot, CANDIDATE_ID)
    await _answer_math_correctly(main, bot, CANDIDATE_ID)
    sent = await send(main.dp, bot, CANDIDATE_ID, text="Mijozlarga xizmat qilishni yaxshi ko'raman")

    assert any("rahmat" in t.lower() for t in _texts_to(sent, CANDIDATE_ID))
    founder_messages = [m for m in sent if getattr(m, "chat_id", None) == FOUNDER_ID]
    assert len(founder_messages) == 1
    # AI ishlamagani uchun shablon (fallback) xulosa ishlatilgan bo'lishi
    # kerak — ``source`` maydoni faqat client mavjudligini bildiradi
    # (bu mavjud xatti-harakat), shuning uchun shablon matndan bilamiz.
    assert "mezon baholandi" in founder_messages[0].text
