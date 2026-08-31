"""Fokus HR — nomzod suhbati end-to-end (Telegram simulyatsiyasi
orqali), Founder karta/qaror, RBAC izolyatsiyasi, bekor qilish/davom
ettirish, moslik filtri (fit) va real Telegram sinovida topilgan
kamchiliklarning tuzatilganini tekshiruvchi regression testlar."""

from datetime import date

import pytest
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import Contact, ReplyKeyboardRemove, Voice

import recruiting_bot
from config import FOUNDER_ID, RECRUITING_BRANCH_ADDRESSES
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


_TEST_BRANCH = "Chilonzor filiali"


async def _start_and_consent(main, bot, candidate_id: int) -> None:
    # ``/apply`` FAQAT aktiv VA kamida bitta filialga biriktirilgan
    # vakansiyani ko'rsatadi (qarang
    # recruiting_bot.py::_vacancies_open_for_candidates). Filialsiz
    # holatni ATAYLAB tekshiradigan
    # ``test_apply_hides_active_vacancy_with_no_branches`` buzilmasin
    # uchun bu global fixture emas, va filial FAQAT hali yo'q bo'lsa
    # biriktiriladi (o'z filiallarini o'zi tayyorlaydigan testlar
    # ustidan yozilmaydi).
    kassir_id = _kassir_id()
    recruiting_repo.set_vacancy_active(kassir_id, True)
    if not recruiting_repo.list_vacancy_branches(kassir_id):
        recruiting_repo.set_vacancy_branches(kassir_id, [{"branch_name": _TEST_BRANCH, "headcount": 1}])
    await send(main.dp, bot, candidate_id, text="/apply")
    await send_callback(main.dp, bot, candidate_id, "rec_consent:yes", target_chat_id=candidate_id)


async def _choose_kassir(main, bot, candidate_id: int) -> None:
    await send_callback(main.dp, bot, candidate_id, f"rec_vacancy:{_kassir_id()}", target_chat_id=candidate_id)


async def _answer_basics(main, bot, candidate_id: int, birth_date: str = "12.10.2000") -> None:
    await send(main.dp, bot, candidate_id, text="Ali Valiyev")  # full_name
    await send(main.dp, bot, candidate_id, text=birth_date)  # birth_date
    await send(main.dp, bot, candidate_id, text="+998901234567")  # phone
    await send(main.dp, bot, candidate_id, text="Toshkent, Chilonzor")  # residence_area
    await send_callback(
        main.dp, bot, candidate_id, f"rec_choice:preferred_branch:{_TEST_BRANCH}", target_chat_id=candidate_id
    )
    await send(main.dp, bot, candidate_id, text="Bir hafta ichida")  # start_date


async def _answer_fit_filter(
    main, bot, candidate_id: int, shift: str = "kunduzgi", holiday: str = "yes", accommodation: str = "yes"
):
    """C bo'limi (moslik filtri) — ``_STEPS_B_C``dagi HAQIQIY tartib.
    ``accommodation_needed`` "yes" bo'lsa oqim to'g'ridan-to'g'ri davom
    etadi, "no" bo'lsa qulaylik follow-up qadami ochiladi (qarang
    ``handle_choice_step_answer``)."""
    await send_callback(main.dp, bot, candidate_id, f"rec_choice:shift_preference:{shift}", target_chat_id=candidate_id)
    await send_callback(main.dp, bot, candidate_id, f"rec_choice:holiday_available:{holiday}", target_chat_id=candidate_id)
    await send(main.dp, bot, candidate_id, text="3 million so'm")  # prev_salary
    await send(main.dp, bot, candidate_id, text="4 million so'm")  # expected_salary
    return await send_callback(
        main.dp, bot, candidate_id, f"rec_choice:accommodation_needed:{accommodation}", target_chat_id=candidate_id
    )


async def _answer_experience(main, bot, candidate_id: int) -> None:
    """D bo'limi (tajriba) — ``_STEPS_D``dagi HAQIQIY tartib."""
    await send(main.dp, bot, candidate_id, text="ABC do'koni, sotuvchi")  # prev_employer
    await send(main.dp, bot, candidate_id, text="2 yil")  # experience_duration
    await send(main.dp, bot, candidate_id, text="2 ta joyda, eng uzog'i 2 yil")  # job_stability
    await send(main.dp, bot, candidate_id, text="Ish joyi uyimga yaqinroq kerak edi")  # leave_reason
    await send_callback(main.dp, bot, candidate_id, "rec_choice:pos_experience:yes", target_chat_id=candidate_id)
    await send(main.dp, bot, candidate_id, text="Qaytim berish va smena yopish tajribam bor")  # cash_handling
    await send_callback(main.dp, bot, candidate_id, "rec_choice:reference_check_consent:yes", target_chat_id=candidate_id)
    # "1yil_plus" — qo'shimcha sabab qadamini ochmaydigan yagona yo'l
    # ("6oygacha" tanlansa alohida follow-up so'raladi).
    await send_callback(
        main.dp, bot, candidate_id, "rec_choice:retention_intent:1yil_plus", target_chat_id=candidate_id
    )
    await send(main.dp, bot, candidate_id, text="Yo'q, xalaqit beradigan holat yo'q")  # attendance_barrier
    await send_callback(main.dp, bot, candidate_id, "rec_choice:substance_policy:yes", target_chat_id=candidate_id)
    await send_callback(main.dp, bot, candidate_id, "rec_choice:criminal_record:no", target_chat_id=candidate_id)


async def _complete_intake(main, bot, candidate_id: int, **fit_kwargs) -> None:
    """Consent'dan tortib D bo'limi oxirigacha (E'dan oldin) — mos
    (fit) holatda, D bo'limi ham so'raladi."""
    await _start_and_consent(main, bot, candidate_id)
    await _choose_kassir(main, bot, candidate_id)
    await _answer_basics(main, bot, candidate_id)
    await _answer_fit_filter(main, bot, candidate_id, **fit_kwargs)
    await _answer_experience(main, bot, candidate_id)


# ``recruiting_questions.CORE_QUESTIONS + OPERATIONAL_QUESTIONS``
# tartibida — har biri aniq (RED emas, UNCLEAR emas) javob, shuning
# uchun hech qaysisiga aniqlashtiruvchi savol berilmaydi.
_SAFE_ROLE_ANSWERS = [
    "Xotirjam tinglab, yechim topishga harakat qilaman",  # core_mijoz_qopol
    "Muqobil mahsulotni taklif qilaman va qachon kelishini aniqlab beraman",  # core_mahsulot_yoq
    "Darhol rahbarga aytaman va yo'l qo'ymayman",  # core_halollik
    "Javonlarni tartibga solaman va mahsulot yetishmasa to'ldiraman",  # core_tashabbus
    "Darhol javondan olib tashlayman va rahbarga xabar beraman",  # core_muddat
]


async def _answer_role_questions_safely(main, bot, candidate_id: int) -> None:
    for answer in _SAFE_ROLE_ANSWERS:
        await send(main.dp, bot, candidate_id, text=answer)


async def _answer_motivation_and_photo(main, bot, candidate_id: int, motivation: str):
    """Motivatsiyadan keyin oxirgi qadam — nomzod rasmi; ariza FAQAT
    rasm kelgach yakunlanadi (qarang ``handle_candidate_photo``)."""
    await send(main.dp, bot, candidate_id, text=motivation)
    return await send(main.dp, bot, candidate_id, photo_file_id="candidate_photo_1")


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

    sent = await _answer_motivation_and_photo(
        main, bot, CANDIDATE_ID, "Mijozlarga xizmat qilishni yaxshi ko'raman"
    )

    candidate_texts = _texts_to(sent, CANDIDATE_ID)
    assert any("rahmat" in t.lower() for t in candidate_texts)
    # Nomzod ballarni yoki ichki tahlilni ko'rmasligi kerak.
    assert not any("ball" in t.lower() for t in candidate_texts)
    assert not any("INTERVIEW_RECOMMENDED" in t for t in candidate_texts)

    # Nomzod fotosi alohida ``send_photo`` bilan ketadi — matnli karta
    # esa aynan BITTA bo'lishi kerak.
    founder_photos = [m for m in sent if isinstance(m, SendPhoto) and m.chat_id == FOUNDER_ID]
    assert len(founder_photos) == 1
    founder_messages = [m for m in sent if isinstance(m, SendMessage) and m.chat_id == FOUNDER_ID]
    assert len(founder_messages) == 1
    founder_card_text = founder_messages[0].text
    assert "Ali Valiyev — Kassir" in founder_card_text
    assert "🤖 AI xulosasi:" in founder_card_text
    assert "📊 Yakuniy tavsiya:" in founder_card_text
    assert "2000" in founder_card_text  # tug'ilgan yil ko'rsatiladi
    # Qarorni har doim Founder qabul qiladi — karta buni aniq aytadi.
    assert "Yakuniy qarorni siz qabul qilasiz" in founder_card_text


async def test_photo_send_is_isolated_from_founder_card_notification():
    """Regressiya: nomzod fotosini Founderga yuborish o'zining alohida
    ``try/except``ida bo'lishi kerak (``recruiting_bot.py``dagi
    ``_run_assessment_and_notify_founder``) — aks holda foto yuborishda
    xato (masalan eskirgan/yaroqsiz file_id yoki vaqtinchalik Telegram
    xatosi) butun bildirishnomani, jumladan matnli nomzod kartasini
    ham, yo'qotib qo'yishi mumkin edi (talab: "Foto bo'lmasa oqim
    yiqilmasin, matnli karta ishlayversin"). Mavjud ``send_photo``
    chaqiruvi (mexanizmi) o'zgartirilmagan — faqat shu chaqiruv atrofida
    izolyatsiya qo'shilgan, shuni manba kodidan tasdiqlaymiz (qarang
    ``test_founder_card_never_targets_a_group_chat``dagi bir xil
    uslub, ``test_recruiting_permissions.py``).
    """
    import inspect

    import recruiting_bot

    source = inspect.getsource(recruiting_bot._run_assessment_and_notify_founder)

    photo_call_index = source.index("send_photo")
    card_call_index = source.index("candidate_review_keyboard")
    try_index = source.rindex("try:", 0, photo_call_index)
    except_index = source.index("except", photo_call_index)

    # ``try:`` foto chaqiruvidan OLDIN, ``except`` undan KEYIN, va
    # matnli karta (``candidate_review_keyboard``) shu try/except'dan
    # KEYIN, unga bog'liq bo'lmagan holda yuboriladi.
    assert try_index < photo_call_index < except_index < card_call_index
    # Mavjud mexanizm (haqiqiy Telegram file_id orqali qayta yuborish)
    # o'zgartirilmagan.
    assert 'application["candidate_photo_file_id"]' in source
    assert "candidate_photo_file_id" in source[:photo_call_index]


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

    sent = await send(main.dp, bot, CANDIDATE_ID, text="/cancel")
    assert "bekor qilindi" in _last_text(sent).lower()
    assert recruiting_repo.get_in_progress_application(CANDIDATE_ID) is None

    cancelled = recruiting_repo.get_application(application["id"])
    assert cancelled["status"] == "cancelled"


async def test_resume_continues_from_saved_step(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")
    await send(main.dp, bot, CANDIDATE_ID, text="12.10.2000")  # birth_date

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

    # Oxirgi savolgacha (core_muddat) — barcha javoblar aniq/xavfsiz.
    for answer in _SAFE_ROLE_ANSWERS[:-1]:
        await send(main.dp, bot, CANDIDATE_ID, text=answer)

    # core_muddat — pozitsiyasi noaniq javob, follow-up kutiladi.
    sent = await send(main.dp, bot, CANDIDATE_ID, text="Xaridorga aytaman")
    follow_up_text = _last_text(sent)
    assert "aniq" in follow_up_text.lower()

    await send(main.dp, bot, CANDIDATE_ID, text="Sotmayman, javondan olib tashlayman")

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

    # Birinchi savolga (core_mijoz_qopol) uchta marta noaniq javob — 2
    # tadan ortiq aniqlashtirish so'ralmasligi va oxir-oqibat keyingi
    # savolga o'tishi kerak.
    for _ in range(3):
        await send(main.dp, bot, CANDIDATE_ID, text=risky)

    # Endi navbatdagi savol (core_mahsulot_yoq)da bo'lishi kerak.
    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    answers = recruiting_repo.get_answers(application["id"])
    first_question_answers = [a for a in answers if a["question_key"] == "core_mijoz_qopol"]
    # Asl javob + eng ko'pi bilan 2 ta follow-up javobi.
    assert len(first_question_answers) <= 3
    assert any(a["question_key"] == "core_mahsulot_yoq" for a in answers)


# ------------------------------------------------------------- moslik filtri --


async def test_underage_candidate_ends_early_with_neutral_message_no_situational_questions(bot_dp):
    """C bo'limi tugagach yosh mos kelmasa, D/E BUTUNLAY so'ralmaydi —
    suhbat neytral yakunlanadi, nomzod "yomon" deb aytilmaydi."""
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    too_young_birth_date = f"12.10.{date.today().year - 14}"
    await _answer_basics(main, bot, CANDIDATE_ID, birth_date=too_young_birth_date)

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
    sent = await _answer_fit_filter(main, bot, CANDIDATE_ID, accommodation="no")

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

    # Motivatsiyadan keyin rasm so'raladi — ariza faqat shundan keyin
    # yakunlanadi va javob DB'ga yoziladi.
    await send(main.dp, bot, CANDIDATE_ID, photo_file_id="candidate_photo_1")

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
    await send(main.dp, bot, CANDIDATE_ID, text="12.10.2000")  # birth_date

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
    await send(main.dp, bot, CANDIDATE_ID, text="12.10.2000")  # birth_date

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
    sent = await _answer_motivation_and_photo(
        main, bot, CANDIDATE_ID, "Mijozlarga xizmat qilishni yaxshi ko'raman"
    )

    assert any("rahmat" in t.lower() for t in _texts_to(sent, CANDIDATE_ID))
    founder_messages = [m for m in sent if isinstance(m, SendMessage) and m.chat_id == FOUNDER_ID]
    assert len(founder_messages) == 1
    # AI ishlamagani uchun shablon (fallback) xulosa ishlatilgan bo'lishi
    # kerak — ``source`` maydoni faqat client mavjudligini bildiradi
    # (bu mavjud xatti-harakat), shuning uchun shablon matndan bilamiz.
    assert "javoblar baholandi (o'rtacha" in founder_messages[0].text


# ------------------------------------------ Founder ishga e'lon berish (main.py) --


def _extract_buttons(sent_message):
    rows = getattr(sent_message.reply_markup, "inline_keyboard", None) or []
    return [button for row in rows for button in row]


async def test_founder_job_ad_single_branch_auto_assigns_full_headcount(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "RECRUITING_BRANCH_NAMES", ["Derizlik", "Charhiy", "Navoiy"])
    kassir = recruiting_repo.get_vacancy_by_key("kassir")

    await send(main.dp, bot, FOUNDER_ID, text="📢 Ishga e'lon berish")
    await send_callback(main.dp, bot, FOUNDER_ID, f"jobad_vac:{kassir['id']}", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_hc:2", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch:0", target_chat_id=FOUNDER_ID)  # Derizlik

    sent = await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch_done", target_chat_id=FOUNDER_ID)
    combined = " ".join(t for t in _texts_to(sent, FOUNDER_ID) if t)
    assert "2 ta" in combined

    # Founder hali "E'lonni tayyorlash" bosmagan -- DBga hech narsa
    # yozilmagan bo'lishi kerak (faqat FSM ichida saqlanadi).
    assert recruiting_repo.list_vacancy_branches(kassir["id"]) == []


async def test_founder_job_ad_multi_branch_requires_matching_sum(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "RECRUITING_BRANCH_NAMES", ["Derizlik", "Charhiy", "Navoiy"])
    kassir = recruiting_repo.get_vacancy_by_key("kassir")

    await send(main.dp, bot, FOUNDER_ID, text="📢 Ishga e'lon berish")
    await send_callback(main.dp, bot, FOUNDER_ID, f"jobad_vac:{kassir['id']}", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_hc:3", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch:0", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch:1", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch_done", target_chat_id=FOUNDER_ID)

    # 1 + 1 = 2, jami 3ga teng emas -- rad etilishi va qaytadan
    # so'ralishi kerak.
    await send(main.dp, bot, FOUNDER_ID, text="1")
    sent = await send(main.dp, bot, FOUNDER_ID, text="1")
    combined = " ".join(t for t in _texts_to(sent, FOUNDER_ID) if t)
    assert "jami 3 ta bo'lishi kerak" in combined

    # Qaytadan to'g'ri taqsimlansa (1 + 2 = 3) qabul qilinadi.
    await send(main.dp, bot, FOUNDER_ID, text="1")
    sent = await send(main.dp, bot, FOUNDER_ID, text="2")
    combined = " ".join(t for t in _texts_to(sent, FOUNDER_ID) if t)
    assert "Yana lavozim qo'shasizmi?" in combined


async def test_founder_job_ad_cannot_finish_branch_selection_with_zero_branches(bot_dp):
    main, bot = bot_dp
    kassir = recruiting_repo.get_vacancy_by_key("kassir")

    await send(main.dp, bot, FOUNDER_ID, text="📢 Ishga e'lon berish")
    await send_callback(main.dp, bot, FOUNDER_ID, f"jobad_vac:{kassir['id']}", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_hc:1", target_chat_id=FOUNDER_ID)

    from aiogram.methods import AnswerCallbackQuery

    sent = await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch_done", target_chat_id=FOUNDER_ID)
    acks = [m for m in sent if isinstance(m, AnswerCallbackQuery)]
    assert any("Kamida 1 ta filial" in (a.text or "") for a in acks)


async def test_founder_job_ad_multiple_positions_and_final_text_shows_only_selected_branches(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "RECRUITING_BRANCH_NAMES", ["Derizlik", "Charhiy", "Navoiy"])
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    sotuvchi = recruiting_repo.get_vacancy_by_key("sotuvchi")

    await send(main.dp, bot, FOUNDER_ID, text="📢 Ishga e'lon berish")
    await send_callback(main.dp, bot, FOUNDER_ID, f"jobad_vac:{kassir['id']}", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_hc:1", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch:0", target_chat_id=FOUNDER_ID)  # Derizlik
    sent = await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch_done", target_chat_id=FOUNDER_ID)
    more_button = next(b for b in _extract_buttons(sent[-1]) if b.callback_data == "jobad_more")
    assert more_button is not None

    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_more", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, f"jobad_vac:{sotuvchi['id']}", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_hc:1", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch:1", target_chat_id=FOUNDER_ID)  # Charhiy
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch_done", target_chat_id=FOUNDER_ID)

    sent = await send_callback(main.dp, bot, FOUNDER_ID, "jobad_finish", target_chat_id=FOUNDER_ID)
    ad_text = _texts_to(sent, FOUNDER_ID)[-1]

    assert "Kassir — 1 ta" in ad_text
    assert "Sotuvchi — 1 ta" in ad_text
    assert "Derizlik — Alisher Navoiy ko'chasi, 76-B uy" in ad_text
    assert "Charhiy — A.T. Xuqandiy mavzesi, 101-A uy" in ad_text
    # Tanlanmagan filial e'londa chiqmaydi. Faqat "Navoiy" so'zini
    # tekshirib bo'lmaydi — Derizlik MANZILIning o'zida "Alisher Navoiy"
    # bor; shuning uchun aynan "Navoiy" filialining e'lon qatori
    # yo'qligini tekshiramiz.
    assert f"Navoiy — {RECRUITING_BRANCH_ADDRESSES['Navoiy']}" not in ad_text
    assert ad_text.count("Derizlik") == 1  # takrorlanmaydi
    assert "?start=apply" in ad_text
    assert "BOT_TOKEN" not in ad_text

    kassir_branches = {b["branch_name"]: b["headcount"] for b in recruiting_repo.list_vacancy_branches(kassir["id"])}
    sotuvchi_branches = {b["branch_name"]: b["headcount"] for b in recruiting_repo.list_vacancy_branches(sotuvchi["id"])}
    assert kassir_branches == {"Derizlik": 1}
    assert sotuvchi_branches == {"Charhiy": 1}
    assert recruiting_repo.get_vacancy(kassir["id"])["is_active"] == 1


async def test_founder_job_ad_replaces_old_branch_assignment_not_merges(bot_dp, monkeypatch):
    main, bot = bot_dp
    monkeypatch.setattr(main, "RECRUITING_BRANCH_NAMES", ["Derizlik", "Charhiy", "Navoiy"])
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Eski filial", "headcount": 9}])

    await send(main.dp, bot, FOUNDER_ID, text="📢 Ishga e'lon berish")
    await send_callback(main.dp, bot, FOUNDER_ID, f"jobad_vac:{kassir['id']}", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_hc:1", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch:0", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_branch_done", target_chat_id=FOUNDER_ID)
    await send_callback(main.dp, bot, FOUNDER_ID, "jobad_finish", target_chat_id=FOUNDER_ID)

    branches = recruiting_repo.list_vacancy_branches(kassir["id"])
    assert [b["branch_name"] for b in branches] == ["Derizlik"]


async def test_invite_flow_still_works_after_job_ad_feature_added(bot_dp):
    """Eski `/invite` (onboarding) oqimi -- "👤 Xodim qo'shish" -- yangi
    "📢 Ishga e'lon berish" tugmasi qo'shilgandan keyin ham
    o'zgarmagan bo'lishi kerak."""
    main, bot = bot_dp

    sent = await send(main.dp, bot, FOUNDER_ID, text="👤 Xodim qo'shish")
    assert any("Kim bo'lib ishlaydi?" in t for t in _texts_to(sent, FOUNDER_ID))


# ----------------------------------------- nomzod: vacancy<->branch filtri --


async def test_apply_hides_active_vacancy_with_no_branches(bot_dp):
    main, bot = bot_dp
    # Standart holatda "kassir"/"sotuvchi" aktiv, lekin hech qanday
    # filialga biriktirilmagan -- nomzodga umuman ko'rinmasligi kerak.
    sent = await send(main.dp, bot, CANDIDATE_ID, text="/apply")
    assert any("Hozircha faol vakansiya mavjud emas" in t for t in _texts_to(sent, CANDIDATE_ID))


async def test_apply_shows_vacancy_once_it_has_at_least_one_branch(bot_dp):
    main, bot = bot_dp
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Derizlik", "headcount": 1}])

    sent = await send(main.dp, bot, CANDIDATE_ID, text="/apply")
    combined = " ".join(t for t in _texts_to(sent, CANDIDATE_ID) if t)
    assert "Boshlaymizmi" in combined


async def test_candidate_sees_only_branches_open_for_chosen_vacancy(bot_dp):
    main, bot = bot_dp
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    sotuvchi = recruiting_repo.get_vacancy_by_key("sotuvchi")
    recruiting_repo.set_vacancy_branches(
        kassir["id"], [{"branch_name": "Derizlik", "headcount": 1}, {"branch_name": "Navoiy", "headcount": 2}]
    )
    recruiting_repo.set_vacancy_branches(sotuvchi["id"], [{"branch_name": "Charhiy", "headcount": 1}])

    await _start_and_consent(main, bot, CANDIDATE_ID)
    sent = await send_callback(
        main.dp, bot, CANDIDATE_ID, f"rec_vacancy:{kassir['id']}", target_chat_id=CANDIDATE_ID
    )
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")
    await send(main.dp, bot, CANDIDATE_ID, text="12.10.2000")  # birth_date
    await send(main.dp, bot, CANDIDATE_ID, text="+998901234567")
    sent = await send(main.dp, bot, CANDIDATE_ID, text="Toshkent")

    buttons = _extract_buttons(sent[-1])
    button_texts = {b.text for b in buttons}
    assert button_texts == {"Derizlik", "Navoiy"}
    assert "Charhiy" not in button_texts  # boshqa vakansiya (sotuvchi)ning filiali


async def test_stale_branch_choice_is_rejected_and_current_buttons_reshown(bot_dp):
    main, bot = bot_dp
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Derizlik", "headcount": 1}])

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await send_callback(main.dp, bot, CANDIDATE_ID, f"rec_vacancy:{kassir['id']}", target_chat_id=CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")
    await send(main.dp, bot, CANDIDATE_ID, text="12.10.2000")  # birth_date
    await send(main.dp, bot, CANDIDATE_ID, text="+998901234567")
    await send(main.dp, bot, CANDIDATE_ID, text="Toshkent")

    # Nomzod ekranida "Derizlik" turgan paytda Founder filialni
    # "Navoiy"ga almashtirib qo'yadi -- eski tanlov endi haqiqiy emas.
    recruiting_repo.clear_vacancy_branches(kassir["id"])
    recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Navoiy", "headcount": 1}])

    sent = await send_callback(
        main.dp, bot, CANDIDATE_ID, "rec_choice:preferred_branch:Derizlik", target_chat_id=CANDIDATE_ID
    )
    buttons = _extract_buttons(sent[-1])
    assert {b.text for b in buttons} == {"Navoiy"}

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["preferred_branch"] is None


# ------------------------------------------------- oddiy fakt step'lar (AI=0) --
# Bu bo'lim ATAYLAB mavjud ``_answer_basics``/``_answer_fit_filter``
# yordamchilaridan mustaqil, faqat ``_STEPS_B_C``/``_STEPS_D``dagi
# HAQIQIY qadam kalitlariga mos xabarlar bilan yuradi (o'sha eski
# yordamchilar boshqa, allaqachon ishlayotgan testlar uchun saqlanadi
# — ularga tegilmagan).


async def _reach_prev_employer_step(main, bot, candidate_id: int):
    await send(main.dp, bot, candidate_id, text="Ali Valiyev")  # full_name
    await send(main.dp, bot, candidate_id, text="12.10.2000")  # birth_date
    await send(main.dp, bot, candidate_id, text="+998901234567")  # phone
    await send(main.dp, bot, candidate_id, text="Toshkent")  # residence_area
    await send_callback(
        main.dp, bot, candidate_id, "rec_choice:preferred_branch:Chilonzor filiali", target_chat_id=candidate_id
    )
    await send(main.dp, bot, candidate_id, text="Bir hafta ichida")  # start_date
    await send_callback(main.dp, bot, candidate_id, "rec_choice:shift_preference:kunduzgi", target_chat_id=candidate_id)
    await send_callback(main.dp, bot, candidate_id, "rec_choice:holiday_available:yes", target_chat_id=candidate_id)
    await send(main.dp, bot, candidate_id, text="3 million so'm")  # prev_salary
    await send(main.dp, bot, candidate_id, text="4 million so'm")  # expected_salary
    # "no" bo'lsa alohida qulaylik-so'rovi (follow-up) qadami ochiladi
    # (qarang ``handle_choice_step_answer``dagi ``accommodation_needed``
    # maxsus holati) -- shu yerda D bo'limiga to'g'ridan-to'g'ri o'tish
    # kerak bo'lgani uchun "yes" ishlatiladi.
    return await send_callback(
        main.dp, bot, candidate_id, "rec_choice:accommodation_needed:yes", target_chat_id=candidate_id
    )


async def test_residence_area_answer_skips_ai_check_and_advances(bot_dp, monkeypatch):
    main, bot = bot_dp
    call_count = 0

    async def _count_off_topic_calls(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return False

    # ``main.py``dagi global ``@dp.errors()`` handler har qanday
    # istisnoni yutib yuboradi -- shuning uchun bu yerda "chaqirilsa
    # xato beradi" o'rniga hisoblagich ishlatiladi (mavjud
    # ``_fail_if_called``/``called`` naqshiga o'xshash).
    monkeypatch.setattr(recruiting_bot.recruiting_followup, "is_off_topic", _count_off_topic_calls)

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")  # full_name
    await send(main.dp, bot, CANDIDATE_ID, text="12.10.2000")  # birth_date
    await send(main.dp, bot, CANDIDATE_ID, text="+998901234567")  # phone

    sent = await send(main.dp, bot, CANDIDATE_ID, text="Qo'qonboy")  # residence_area

    assert call_count == 0
    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["residence_area"] == "Qo'qonboy"
    assert "Qaysi filialda ishlamoqchisiz?" in _last_text(sent)


async def test_prev_employer_free_text_skips_ai_check_and_advances(bot_dp, monkeypatch):
    main, bot = bot_dp
    call_count = 0

    async def _count_off_topic_calls(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return False

    monkeypatch.setattr(recruiting_bot.recruiting_followup, "is_off_topic", _count_off_topic_calls)

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    reach_sent = await _reach_prev_employer_step(main, bot, CANDIDATE_ID)
    prompt_message = reach_sent[-1]
    assert prompt_message.reply_markup.keyboard[0][0].text == "❌ Oldin ishlamaganman"

    sent = await send(main.dp, bot, CANDIDATE_ID, text="Correon do'koni, sotuvchi")

    assert call_count == 0
    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["prev_employer_text"] == "Correon do'koni, sotuvchi"
    assert "necha yil" in _last_text(sent).lower()


async def test_prev_employer_no_experience_button_stores_canonical_value_and_clears_keyboard(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _reach_prev_employer_step(main, bot, CANDIDATE_ID)

    sent = await send(main.dp, bot, CANDIDATE_ID, text="❌ Oldin ishlamaganman")

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["prev_employer_text"] == "yo'q"

    next_prompt = sent[-1]
    assert "necha yil" in (next_prompt.text or "").lower()
    assert isinstance(next_prompt.reply_markup, ReplyKeyboardRemove)


async def test_leave_reason_step_is_not_in_ai_free_bypass_list():
    """Faqat listed AI-free step_key'lardan tashqarida hech narsa
    o'zgarmagan -- ``leave_reason`` hozirgidek AI/off-topic
    tekshiruvidan (va follow-up mantig'idan) o'tishda davom etadi."""
    assert "leave_reason" not in recruiting_bot._AI_FREE_FACT_STEPS


# ------------------------------------------------ headcount != application cap --


async def test_headcount_does_not_cap_candidate_applications(bot_dp):
    """Bug: vakansiyaning ``headcount``i (Founder rejalashtirgan xodim
    soni) ariza/application limiti EMAS -- headcountdan ko'p ariza
    mavjud bo'lsa ham, vakansiya yangi nomzodlarga ko'rinishda va
    ``/apply`` oqimiga ochiq bo'lib qolishi kerak."""
    main, bot = bot_dp
    kassir = recruiting_repo.get_vacancy_by_key("kassir")
    recruiting_repo.set_vacancy_branches(kassir["id"], [{"branch_name": "Chilonzor filiali", "headcount": 1}])

    for i in range(5):
        recruiting_repo.create_application(700000 + i, kassir["id"], "2099-01-01T00:00:00+00:00")

    sent = await send(main.dp, bot, CANDIDATE_ID, text="/apply")
    combined = " ".join(t for t in _texts_to(sent, CANDIDATE_ID) if t)
    assert "Boshlaymizmi" in combined
