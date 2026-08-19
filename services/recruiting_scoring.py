"""Nomzod javoblarini baholash: DETERMINISTIK yadro (rubrika ballari va
yakuniy natija — ``overall_result``) + ixtiyoriy AI qisqa xulosa matni.

Muhim: ``overall_result`` (INTERVIEW_RECOMMENDED / NEEDS_HUMAN_REVIEW /
REQUIREMENT_MISMATCH) HAR DOIM shu moduldagi qat'iy qoidalar bilan
hisoblanadi — AI bu qarorni HECH QACHON o'zgartirmaydi yoki
chiqarmaydi, faqat (mavjud bo'lsa) transkriptga asoslangan qisqa,
tabiiy matnli xulosa yozadi. AI ishlamasa yoki noto'g'ri/uzun natija
bersa, oddiy shablon xulosa ishlatiladi — baholash hech qachon
to'xtamaydi.

REAL TELEGRAM SINOVIDA topilgan asosiy kamchilik: eski versiya
mazmundan qat'i nazar faqat javob UZUNLIGIGA qarab ball berardi
(``_score_by_length``) — shu sabab xavfli javoblar ham "uzun/aniq"
bo'lgani uchun yaxshi baholanardi. Endi ``kassa_xavfsizlik``,
``muddat_xavfsizligi``, ``javobgarlik`` va ``muomala`` (mojaro savoli)
mezonlari ``services/recruiting_redflags.py`` orqali MAZMUNGA qarab
baholanadi:

- kritik RED signal topilsa — ball 0 VA ``red_flags`` ro'yxatiga
  qo'shiladi. Kritik red flag mavjud bo'lsa, yakuniy natija HECH
  QACHON ``INTERVIEW_RECOMMENDED`` bo'lmaydi (qarang ``_overall_result``).
- javob berilmagan bo'lsa — ball ``None`` (o'rtacha ballga QO'SHILMAYDI,
  "javobsiz savolga ball berilmaydi").
- javob ikkilanuvchan (UNCLEAR) bo'lsa — ball ``None`` va savol
  ``clarify_questions``ga qo'shiladi (Founderga "suhbatda aniqlashtiring"
  deb ko'rsatiladi) — bitta yaxshi kalit so'z butun javobni avtomatik
  yaxshi qilib bermaydi.

Himoyalangan shaxsiy xususiyatlar (din, millat, oilaviy holat va h.k.)
BU YERDA UMUMAN YO'Q — ular hech qachon so'ralmagani uchun ballga ham
ta'sir qila olmaydi. Tug'ilgan yil ham shu sabab bu yerda UMUMAN
ishlatilmaydi (faqat FSM darajasida qonuniy yosh tekshiruvi uchun,
qarang ``recruiting_bot.py``).
"""

import json
import logging

from openai import AsyncOpenAI

from services import recruiting_redflags, recruiting_rubric

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"
# Founder kartasi endi QISQA (15-20 soniyada o'qiladigan) bo'lishi
# kerak — xulosa 2-3 juda qisqa jumladan oshmasin.
_MAX_SUMMARY_LEN = 260

RESULT_INTERVIEW = "INTERVIEW_RECOMMENDED"
RESULT_NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"
RESULT_MISMATCH = "REQUIREMENT_MISMATCH"

# Mezon kaliti -> lavozim -> savol kalitlari. Shu mezonlar UZUNLIKKA
# emas, MAZMUNGA qarab (``recruiting_redflags`` orqali) baholanadi.
_REDFLAG_CRITERIA_QUESTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "kassa_xavfsizlik": {"kassir": ("kassir_login",)},
    "muddat_xavfsizligi": {"kassir": ("kassir_muddat",), "sotuvchi": ("sotuvchi_muddat",)},
    "javobgarlik": {"kassir": ("kassir_kamomad", "kassir_javobgarlik")},
    "muomala": {"kassir": ("kassir_janjal",), "sotuvchi": ("sotuvchi_norozilik",)},
    "halollik": {"kassir": ("umumiy_ogirlik_guvoh",), "sotuvchi": ("umumiy_ogirlik_guvoh",)},
}
_REDFLAG_CHECKER: dict[str, "callable[[str], str]"] = {
    "kassa_xavfsizlik": recruiting_redflags.check_credential_sharing,
    "muddat_xavfsizligi": recruiting_redflags.check_expired_product,
    "javobgarlik": recruiting_redflags.check_shortage_response,
    "muomala": recruiting_redflags.check_customer_conflict,
    "halollik": recruiting_redflags.check_theft_witness,
}
_REDFLAG_FLAG_KEY: dict[str, str] = {
    "kassa_xavfsizlik": recruiting_redflags.CREDENTIAL_SHARING,
    "muddat_xavfsizligi": recruiting_redflags.EXPIRED_PRODUCT,
    "javobgarlik": recruiting_redflags.SHORTAGE_COVERUP,
    "muomala": recruiting_redflags.CUSTOMER_CONFLICT,
    "halollik": recruiting_redflags.THEFT_COVERUP,
}

_KASSIR_CRITERION_QUESTIONS: dict[str, list[str]] = {
    "muammo_yechish": ["kassir_narx_farqi", "kassir_telefon", "umumiy_kech_qolish"],
}
_SOTUVCHI_CRITERION_QUESTIONS: dict[str, list[str]] = {
    "ehtiyoj": ["sotuvchi_ehtiyoj", "sotuvchi_kutib_olish"],
    "tavsiya": ["sotuvchi_qoshimcha", "sotuvchi_topilmasa"],
    "javon": ["sotuvchi_javon", "umumiy_kech_qolish"],
    "jamoaviylik": ["sotuvchi_kelishmovchilik"],
}
_CRITERION_QUESTIONS_BY_POSITION = {
    "kassir": _KASSIR_CRITERION_QUESTIONS,
    "sotuvchi": _SOTUVCHI_CRITERION_QUESTIONS,
}

_GENERIC_VAGUE_PHRASES = (
    "bilmayman", "bilmadim", "farqi yo'q", "shunchaki", "hech narsa", "nima desam",
)


def _answers_by_key(answers: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for answer in answers:
        grouped.setdefault(answer["question_key"], []).append(answer)
    return grouped


def _evidence(text: str, limit: int = 110) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _score_by_length(combined_text: str) -> int:
    text = combined_text.strip()
    length = len(text)
    if length == 0:
        return 0
    if any(phrase in text.lower() for phrase in _GENERIC_VAGUE_PHRASES):
        return min(1, 1 if length >= 5 else 0)
    if length >= 20:
        return 2
    if length >= 5:
        return 1
    return 0


def _is_still_vague_or_offtopic(text: str) -> bool:
    """Bitta/ikkita aniqlashtirish urinishidan KEYIN ham javob hali
    mazmunsiz/aloqasiz bo'lib qolsa — "ijobiy ball berilmasin,
    aniqlashtirish kerak deb belgilansin" (real Telegram sinovidan
    keyingi talab). Faqat oxirgi (barcha follow-up bilan birlashtirilgan)
    matnga qo'llaniladi."""
    stripped = text.strip()
    if len(stripped) < 5:
        return True
    lowered = stripped.lower()
    return any(phrase in lowered for phrase in _GENERIC_VAGUE_PHRASES)


def _combined_answer_text(grouped_answers: dict[str, list[dict]], question_keys: tuple[str, ...]) -> tuple[str, str]:
    """(asl_javob, keyingi_aniqlashtirish_matni) — ikkalasi alohida,
    chunki qaror avval aslidan, keyin (agar xavfli bo'lsa) aniqlashtirish
    javobidan ham kelib chiqadi (qarang mavjud ``kassa_xavfsizlik``
    naqshi — nomzod follow-up'da fikridan qaytishi mumkin)."""
    entries: list[dict] = []
    for q_key in question_keys:
        entries.extend(grouped_answers.get(q_key, []))
    if not entries:
        return "", ""
    original = " ".join(e["answer_text"] for e in entries if not e.get("is_follow_up"))
    follow_up = " ".join(e["answer_text"] for e in entries if e.get("is_follow_up"))
    return original, follow_up


def _score_redflag_criterion(
    grouped_answers: dict[str, list[dict]], question_keys: tuple[str, ...], checker, flag_key: str
) -> tuple[int | None, str, dict | None, bool]:
    """Qaytaradi: (ball yoki None, dalil matni, red_flag yozuvi yoki
    None, aniqlashtirish_kerak: bool)."""
    original, follow_up = _combined_answer_text(grouped_answers, question_keys)
    if not original.strip():
        return None, "Javob berilmagan.", None, False

    status = checker(original)
    evidence_text = original
    if follow_up.strip():
        # Aniqlashtirish javobini ALOHIDA tekshiramiz (birlashtirilgan
        # matnda emas) — aks holda asl xavfli ibora combined matnda
        # baribir qolib, "ikkalasi ham bor -> RED" qoidasi orqali
        # chinakam fikridan qaytishni ham RED qilib qo'yardi. Nomzod
        # aniq fikridan qaytsa (follow-up ALOHIDA GREEN), red flag olib
        # tashlanadi; yana ham xavfli javob bersa (follow-up ALOHIDA
        # RED), RED holicha qoladi; follow-up o'zi ham noaniq bo'lsa,
        # ASL javobning holati saqlanadi.
        follow_up_status = checker(follow_up)
        evidence_text = f"{original} {follow_up}"
        if follow_up_status in (recruiting_redflags.RED, recruiting_redflags.GREEN):
            status = follow_up_status

    if status == recruiting_redflags.RED:
        red_flag = {
            "key": flag_key,
            "label": recruiting_redflags.label_for(flag_key),
            "evidence": _evidence(evidence_text),
        }
        return 0, _evidence(evidence_text), red_flag, False

    if status == recruiting_redflags.GREEN:
        return 2, _evidence(evidence_text), None, False

    # UNCLEAR — ikkalasi ham aniq emas: ball berilmaydi, Founder
    # suhbatda aniqlashtirsin (AI/deterministik tizim ma'no o'ylab
    # topmaydi).
    return None, _evidence(evidence_text) or "Javob noaniq.", None, True


def _scan_for_physical_aggression(grouped_answers: dict[str, list[dict]]) -> list[dict]:
    """Jismoniy tahdid ISTALGAN savolda chiqib qolishi mumkin — bitta
    rubrika mezoniga bog'lanmagan, shuning uchun transkriptdagi barcha
    savol kalitlari bo'yicha alohida skanerlanadi (retraction mantig'i
    ``_score_redflag_criterion`` bilan bir xil: follow-up'da chindan
    fikridan qaytsa, red flag qo'yilmaydi)."""
    flags: list[dict] = []
    for question_keys in [(key,) for key in grouped_answers]:
        _, _, red_flag, _ = _score_redflag_criterion(
            grouped_answers, question_keys, recruiting_redflags.check_physical_aggression,
            recruiting_redflags.PHYSICAL_AGGRESSION,
        )
        if red_flag:
            flags.append(red_flag)
    return flags


def _score_jadval_moslik(availability_text: str | None) -> tuple[int | None, str]:
    if not availability_text or not availability_text.strip():
        return None, "Ish jadvaliga moslik haqida ma'lumot berilmagan."
    return 1, _evidence(availability_text)


def score_application(
    position_key: str,
    application: dict,
    answers: list[dict],
    math_correct: bool | None,
) -> dict:
    criteria = recruiting_rubric.criteria_for(position_key)
    grouped_answers = _answers_by_key(answers)
    criterion_question_map = _CRITERION_QUESTIONS_BY_POSITION.get(position_key, {})

    criteria_scores: list[dict] = []
    red_flags: list[dict] = []
    clarify_questions: list[str] = []
    has_unclear_critical = False

    for criterion in criteria:
        key, label = criterion["key"], criterion["label"]
        redflag_question_keys = _REDFLAG_CRITERIA_QUESTIONS.get(key, {}).get(position_key)

        if redflag_question_keys:
            checker = _REDFLAG_CHECKER[key]
            flag_key = _REDFLAG_FLAG_KEY[key]
            score, evidence, red_flag, unclear = _score_redflag_criterion(
                grouped_answers, redflag_question_keys, checker, flag_key
            )
            if red_flag:
                red_flags.append(red_flag)
            if unclear:
                has_unclear_critical = True
                present = [qk for qk in redflag_question_keys if qk in grouped_answers]
                if present:
                    q_text = grouped_answers[present[0]][0]["question_text"]
                    clarify_questions.append(q_text)
        elif key == "tajriba":
            text = " ".join(
                filter(None, [application.get("prev_employer_text"), application.get("experience_duration_text"), application.get("experience_text")])
            )
            score = _score_by_length(text) if text.strip() else None
            evidence = _evidence(text) or "Ma'lumot berilmagan."
        elif key == "matematik":
            if math_correct is None:
                score, evidence = None, "Matematik savol berilmagan."
            else:
                score = 2 if math_correct else 0
                evidence = "To'g'ri javob berdi." if math_correct else "Noto'g'ri javob berdi."
        elif key == "jadval_moslik":
            score, evidence = _score_jadval_moslik(application.get("availability_text"))
        else:
            question_keys = tuple(criterion_question_map.get(key, []))
            original, follow_up = _combined_answer_text(grouped_answers, question_keys)
            combined = f"{original} {follow_up}".strip()
            if not combined:
                score, evidence = None, "Javob berilmagan."
            elif follow_up.strip() and _is_still_vague_or_offtopic(combined):
                # Aniqlashtiruvchi savoldan KEYIN ham hali mazmunsiz/aloqasiz —
                # ball berilmaydi, Founder suhbatda aniqlashtirsin.
                score, evidence = None, _evidence(combined) or "Javob noaniq."
                present = [qk for qk in question_keys if qk in grouped_answers]
                if present:
                    clarify_questions.append(grouped_answers[present[0]][0]["question_text"])
            else:
                score = _score_by_length(combined)
                evidence = _evidence(combined) or "Javob berilmagan."

        criteria_scores.append({"key": key, "label": label, "score": score, "evidence": evidence})

    if application.get("property_honesty_flag"):
        # "Nega ketgansiz" ochiq savoliga javob berayotganda nomzod
        # o'zi do'kon mahsulotini ruxsatsiz olgan/yeganini aytib
        # qo'ygan (qarang recruiting_bot._handle_leave_reason_answer) —
        # bu rubrika mezoni EMAS (alohida savol emas), shuning uchun
        # to'g'ridan-to'g'ri red_flags ro'yxatiga qo'shiladi. Yakuniy
        # qarorni baribir Founder beradi (qarang _overall_result).
        evidence_text = " ".join(
            filter(None, [application.get("leave_reason_text"), application.get("leave_reason_followup_text")])
        )
        red_flags.append({
            "key": recruiting_redflags.PROPERTY_HONESTY,
            "label": recruiting_redflags.label_for(recruiting_redflags.PROPERTY_HONESTY),
            "evidence": _evidence(evidence_text),
        })

    # Jismoniy tahdid har qanday savolda chiqib qolishi mumkin (faqat
    # "xaridor bilan mojaro" savoli emas) — butun transkript skanerlanadi.
    red_flags.extend(_scan_for_physical_aggression(grouped_answers))

    overall_result = _overall_result(criteria_scores, math_correct, position_key, red_flags, has_unclear_critical)
    strengths = [c["label"] for c in criteria_scores if c["score"] == 2][:3]
    # Red-flag mezonlarining 0 balli allaqachon ``red_flags``da alohida
    # qayd etilgan (masalan "kassa_xavfsizlik") — bu yerda takrorlanmasin
    # (Founder kartasida bir xil signal ikki marta ko'rsatilmasligi kerak).
    risks = [
        {"criterion": c["label"], "evidence": c["evidence"]}
        for c in criteria_scores
        if c["score"] == 0 and c["key"] not in _REDFLAG_CRITERIA_QUESTIONS
    ][:3]

    return {
        "criteria_scores": criteria_scores,
        "overall_result": overall_result,
        "strengths": strengths,
        "risks": risks,
        "red_flags": red_flags,
        "clarify_questions": clarify_questions[:4],
    }


def _overall_result(
    criteria_scores: list[dict],
    math_correct: bool | None,
    position_key: str,
    red_flags: list[dict],
    has_unclear_critical: bool,
) -> str:
    # Kritik xavf — hech qachon avtomatik "Suhbatga tavsiya" chiqmaydi,
    # ball qanchalik yuqori bo'lishidan qat'i nazar.
    if red_flags:
        return RESULT_NEEDS_REVIEW

    if has_unclear_critical:
        return RESULT_NEEDS_REVIEW

    if position_key == "kassir" and math_correct is False:
        return RESULT_NEEDS_REVIEW

    scores = [c["score"] for c in criteria_scores if c["score"] is not None]
    if not scores:
        return RESULT_NEEDS_REVIEW

    average = sum(scores) / len(scores)
    if average >= 1.5:
        return RESULT_INTERVIEW
    if average <= 0.5:
        return RESULT_MISMATCH
    return RESULT_NEEDS_REVIEW


def _fallback_summary(position_key: str, deterministic_result: dict) -> str:
    scores = [c["score"] for c in deterministic_result["criteria_scores"] if c["score"] is not None]
    average = round(sum(scores) / len(scores), 1) if scores else 0
    red_flag_note = ""
    if deterministic_result.get("red_flags"):
        red_flag_note = f" {len(deterministic_result['red_flags'])} ta jiddiy signal aniqlandi."
    return f"{position_key.capitalize()} lavozimi bo'yicha javoblar baholandi (o'rtacha {average}/2).{red_flag_note}"


def _parse_json(raw: str) -> dict | None:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def _ai_summary(
    client: AsyncOpenAI, position_key: str, answers: list[dict], deterministic_result: dict
) -> str | None:
    transcript = "\n".join(f"- {a['question_text']}\n  Javob: {a['answer_text']}" for a in answers)
    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                "Sen ishga qabul jarayonida Founderga yordam beruvchi tahlilchisan. "
                "Founder buni 15-20 soniyada o'qib tushunishi kerak — shuning uchun "
                "FAQAT 2-3 ta JUDA QISQA, oddiy o'zbek tilidagi jumla yoz (rasmiy HR "
                "atamalarisiz, uzun gaplarsiz). Faqat berilgan savol-javoblar asosida, "
                "HECH QANDAY yangi fakt yoki raqam o'ylab topmasdan yoz. Nomzodni "
                "ayblama, haqorat qilma yoki shaxsi ustidan baho berma (masalan 'menga "
                "yoqdi' kabi) — faqat faktlarga tayan. Yakuniy natijani (masalan "
                "'suhbatga tavsiya etiladi' yoki 'qo'lda ko'rib chiqish kerak') AYTMA — "
                "karta buni allaqachon alohida ko'rsatadi, sen faqat qisqa faktik "
                "kuzatuv yoz. Masalan: \"Savdo tajribasi bor, mijoz bilan muomalasi "
                "yaxshi. Halollik bo'yicha bitta savolni Founder aniqlashtirishi "
                "kerak.\" Faqat quyidagi JSON formatida javob qaytar, boshqa hech "
                'narsa yozma: {"summary": "xulosa matni"}'
            ),
            input=f"Lavozim: {position_key}\n\nSavol-javoblar:\n{transcript}",
        )
        data = _parse_json(response.output_text or "")
        if data is None:
            return None
        summary = data.get("summary")
        if not isinstance(summary, str):
            return None
        summary = summary.strip()
        if not summary or len(summary) > _MAX_SUMMARY_LEN:
            return None
        return summary
    except Exception as error:  # noqa: BLE001 - AI xatosi baholashni to'xtatmasin
        logger.warning("OpenAI xatosi (recruiting summary): %r", error)
        return None


async def summarize(
    client: AsyncOpenAI | None, position_key: str, answers: list[dict], deterministic_result: dict
) -> str:
    if client is not None:
        ai_result = await _ai_summary(client, position_key, answers, deterministic_result)
        if ai_result:
            return ai_result

    return _fallback_summary(position_key, deterministic_result)
