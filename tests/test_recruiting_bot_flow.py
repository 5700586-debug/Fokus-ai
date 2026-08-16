"""Fokus HR — nomzod suhbati end-to-end (Telegram simulyatsiyasi
orqali), Founder karta/qaror, RBAC izolyatsiyasi va bekor
qilish/davom ettirish uchun testlar."""

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


async def _answer_common_fields(main, bot, candidate_id: int) -> None:
    await send(main.dp, bot, candidate_id, text="Ali Valiyev")  # full_name
    await send(main.dp, bot, candidate_id, text="+998901234567")  # phone
    await send(main.dp, bot, candidate_id, text="2 yil sotuvda ishlaganman")  # experience
    await send(main.dp, bot, candidate_id, text="Ish joyi uyimga yaqinroq kerak edi")  # leave_reason
    await send(main.dp, bot, candidate_id, text="Har kuni ishlay olaman")  # availability
    await send(main.dp, bot, candidate_id, text="Bir hafta ichida")  # start_date


_SAFE_KASSIR_ANSWERS = [
    "Darhol rahbarga aytib, hisobni tekshiraman",
    "Narxni tekshirib, xaridorga tushuntiraman",
    "Ishdan keyin qo'ng'iroq qilaman",
    "Hech kimga bermayman, faqat o'zim ishlataman",
    "Kassa egasi javobgar bo'lishi kerak deb o'ylayman",
    "Xotirjam tinglab, yechim topishga harakat qilaman",
    "Darhol chetga olib, rahbarga aytaman",
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

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _answer_common_fields(main, bot, CANDIDATE_ID)
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
    await send(main.dp, bot, CANDIDATE_ID, text="+998901234567")

    # "Restart" simulyatsiyasi: xuddi shu foydalanuvchi /apply'ni qayta
    # bosadi — DB'dagi tugallanmagan ariza asosida davom etishi kerak,
    # yangi ariza yaratmasligi kerak.
    application_before = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    sent = await send(main.dp, bot, CANDIDATE_ID, text="/apply")

    assert any("saqlangan" in t.lower() for t in _texts_to(sent, CANDIDATE_ID))
    application_after = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application_before["id"] == application_after["id"]

    # Davom etib, tajriba savoliga to'g'ri javob berish kerak (chunki
    # keyingi qadam "experience" bo'lishi kerak, "full_name" emas).
    await send(main.dp, bot, CANDIDATE_ID, text="1 yil tajribam bor")
    updated = recruiting_repo.get_application(application_after["id"])
    assert updated["experience_text"] == "1 yil tajribam bor"


# ------------------------------------------------------------ moslashuvchan --


async def test_risky_answer_triggers_follow_up_and_records_it(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _answer_common_fields(main, bot, CANDIDATE_ID)

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)

    # kassir_kamomad, kassir_narx_farqi, kassir_telefon — xavfsiz javoblar.
    await send(main.dp, bot, CANDIDATE_ID, text="Darhol rahbarga aytaman")
    await send(main.dp, bot, CANDIDATE_ID, text="Narxni tekshiraman")
    await send(main.dp, bot, CANDIDATE_ID, text="Keyinroq qo'ng'iroq qilaman")

    # kassir_login — xavfli javob, follow-up kutiladi.
    sent = await send(main.dp, bot, CANDIDATE_ID, text="Ishongan eski xodimga kassamni beraman")
    follow_up_text = _last_text(sent)
    assert "javobgar" in follow_up_text.lower()

    await send(main.dp, bot, CANDIDATE_ID, text="Yo'q, albatta men javobgar bo'laman")

    answers = recruiting_repo.get_answers(application["id"])
    follow_up_answers = [a for a in answers if a["is_follow_up"]]
    assert len(follow_up_answers) == 1


async def test_max_two_follow_ups_per_application(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _answer_common_fields(main, bot, CANDIDATE_ID)

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    risky = "Bilmayman, hech narsa qilmayman"

    for _ in range(7):
        await send(main.dp, bot, CANDIDATE_ID, text=risky)

    updated = recruiting_repo.get_application(application["id"])
    assert updated["follow_up_count"] <= 2


# ------------------------------------------------------------------- ovoz --


async def test_voice_too_long_is_rejected_and_asks_for_shorter(bot_dp, monkeypatch):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _answer_common_fields(main, bot, CANDIDATE_ID)
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

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _answer_common_fields(main, bot, CANDIDATE_ID)
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

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await _answer_common_fields(main, bot, CANDIDATE_ID)
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

    message = make_message(CANDIDATE_ID, text=None)
    message = message.model_copy(
        update={"contact": Contact(phone_number="+998901112233", first_name="Ali")}
    )
    from aiogram.types import Update

    bot.sent = []
    await main.dp.feed_update(bot, Update(update_id=1, message=message))

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["phone"] == "+998901112233"


async def test_invalid_phone_text_is_rejected(bot_dp):
    main, bot = bot_dp

    await _start_and_consent(main, bot, CANDIDATE_ID)
    await _choose_kassir(main, bot, CANDIDATE_ID)
    await send(main.dp, bot, CANDIDATE_ID, text="Ali Valiyev")

    sent = await send(main.dp, bot, CANDIDATE_ID, text="qwerty")
    assert "noto'g'ri" in _last_text(sent).lower()

    application = recruiting_repo.get_in_progress_application(CANDIDATE_ID)
    assert application["phone"] is None
