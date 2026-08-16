"""Nomzod javoblarini baholash: DETERMINISTIK yadro (rubrika ballari va
yakuniy natija — ``overall_result``) + ixtiyoriy AI qisqa xulosa matni.

Muhim: ``overall_result`` (INTERVIEW_RECOMMENDED / NEEDS_HUMAN_REVIEW /
REQUIREMENT_MISMATCH) HAR DOIM shu moduldagi qat'iy qoidalar bilan
hisoblanadi — AI bu qarorni HECH QACHON o'zgartirmaydi yoki
chiqarmaydi, faqat (mavjud bo'lsa) transkriptga asoslangan qisqa,
tabiiy matnli xulosa yozadi. AI ishlamasa yoki noto'g'ri/uzun natija
bersa, oddiy shablon xulosa ishlatiladi — baholash hech qachon
to'xtamaydi.

Himoyalangan shaxsiy xususiyatlar (din, millat, oilaviy holat va h.k.)
BU YERDA UMUMAN YO'Q — ular hech qachon so'ralmagani uchun ballga ham
ta'sir qila olmaydi.
"""

import json
import logging

from openai import AsyncOpenAI

from services import recruiting_followup, recruiting_rubric

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"
_MAX_SUMMARY_LEN = 400

RESULT_INTERVIEW = "INTERVIEW_RECOMMENDED"
RESULT_NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"
RESULT_MISMATCH = "REQUIREMENT_MISMATCH"

_KASSIR_CRITERION_QUESTIONS: dict[str, list[str]] = {
    "muomala": ["kassir_janjal"],
    "muammo_yechish": ["kassir_narx_farqi", "kassir_muddat"],
    "javobgarlik": ["kassir_kamomad", "kassir_javobgarlik"],
}
_SOTUVCHI_CRITERION_QUESTIONS: dict[str, list[str]] = {
    "muomala": ["sotuvchi_kutib_olish", "sotuvchi_norozilik"],
    "ehtiyoj": ["sotuvchi_ehtiyoj"],
    "tavsiya": ["sotuvchi_qoshimcha", "sotuvchi_topilmasa"],
    "javon": ["sotuvchi_javon", "sotuvchi_muddat"],
    "muammo_yechish": ["sotuvchi_norozilik"],
    "jamoaviylik": ["sotuvchi_kelishmovchilik"],
}
_CRITERION_QUESTIONS_BY_POSITION = {
    "kassir": _KASSIR_CRITERION_QUESTIONS,
    "sotuvchi": _SOTUVCHI_CRITERION_QUESTIONS,
}


def _answers_by_key(answers: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for answer in answers:
        grouped.setdefault(answer["question_key"], []).append(answer)
    return grouped


def _evidence(text: str, limit: int = 110) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _score_by_length(combined_text: str) -> int:
    length = len(combined_text.strip())
    if length >= 20:
        return 2
    if length >= 5:
        return 1
    return 0


def _score_kassa_xavfsizlik(grouped_answers: dict[str, list[dict]]) -> tuple[int, str]:
    entries = grouped_answers.get("kassir_login", [])
    if not entries:
        return 1, "Javob berilmagan."

    original = entries[0]["answer_text"]
    follow_up_text = " ".join(e["answer_text"] for e in entries[1:])
    risky = recruiting_followup.deterministic_follow_up(original) is not None

    if not risky:
        return 2, _evidence(original)

    reassuring_phrases = ("bermayman", "hech kimga bermayman", "faqat o'zim", "hech qachon bermayman")
    if follow_up_text and any(phrase in follow_up_text.lower() for phrase in reassuring_phrases):
        return 2, _evidence(follow_up_text)

    return 0, _evidence(original)


def _score_jadval_moslik(availability_text: str | None) -> tuple[int, str]:
    if not availability_text or not availability_text.strip():
        return 0, "Ish jadvaliga moslik haqida ma'lumot berilmagan."
    # Vakansiyaning aniq jadval talabi (schedule_description) odatda
    # sozlanmagan bo'lishi mumkin — bunday holatda taqqoslash uchun
    # yetarli ma'lumot yo'q, shuning uchun "noaniq" (1) deb belgilanadi,
    # mos EMAS (0) deb hukm qilinmaydi.
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
    for criterion in criteria:
        key, label = criterion["key"], criterion["label"]

        if key == "tajriba":
            text = application.get("experience_text") or ""
            score = _score_by_length(text)
            evidence = _evidence(text) or "Ma'lumot berilmagan."
        elif key == "kassa_xavfsizlik":
            score, evidence = _score_kassa_xavfsizlik(grouped_answers)
        elif key == "matematik":
            if math_correct is None:
                score, evidence = 1, "Matematik savol berilmagan."
            else:
                score = 2 if math_correct else 0
                evidence = "To'g'ri javob berdi." if math_correct else "Noto'g'ri javob berdi."
        elif key == "jadval_moslik":
            score, evidence = _score_jadval_moslik(application.get("availability_text"))
        else:
            question_keys = criterion_question_map.get(key, [])
            texts = [
                entry["answer_text"]
                for q_key in question_keys
                for entry in grouped_answers.get(q_key, [])
            ]
            combined = " ".join(texts)
            score = _score_by_length(combined)
            evidence = _evidence(combined) or "Javob berilmagan."

        criteria_scores.append({"key": key, "label": label, "score": score, "evidence": evidence})

    overall_result = _overall_result(criteria_scores, math_correct, position_key)
    strengths = [c["label"] for c in criteria_scores if c["score"] == 2][:3]
    risks = [
        {"criterion": c["label"], "evidence": c["evidence"]}
        for c in criteria_scores
        if c["score"] == 0
    ][:3]

    return {
        "criteria_scores": criteria_scores,
        "overall_result": overall_result,
        "strengths": strengths,
        "risks": risks,
    }


def _overall_result(criteria_scores: list[dict], math_correct: bool | None, position_key: str) -> str:
    security_score = next((c["score"] for c in criteria_scores if c["key"] == "kassa_xavfsizlik"), None)
    if security_score == 0:
        return RESULT_MISMATCH

    if position_key == "kassir" and math_correct is False:
        return RESULT_NEEDS_REVIEW

    scores = [c["score"] for c in criteria_scores]
    if not scores:
        return RESULT_NEEDS_REVIEW

    average = sum(scores) / len(scores)
    if average >= 1.5:
        return RESULT_INTERVIEW
    if average <= 0.5:
        return RESULT_MISMATCH
    return RESULT_NEEDS_REVIEW


def _fallback_summary(position_key: str, deterministic_result: dict) -> str:
    scores = [c["score"] for c in deterministic_result["criteria_scores"]]
    average = round(sum(scores) / len(scores), 1) if scores else 0
    return (
        f"{position_key.capitalize()} lavozimi bo'yicha {len(scores)} mezon baholandi, "
        f"o'rtacha ball: {average}/2. To'liq tafsilotlar mezonlar jadvalida."
    )


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
                "Faqat berilgan savol-javoblar asosida, HECH QANDAY yangi fakt yoki "
                "raqam o'ylab topmasdan, 2-3 jumlali qisqa, xolis, o'zbek tilidagi xulosa "
                "yoz. Nomzodni ayblama yoki maqtab yubormang — faktlarga tayangan holda "
                "yoz. Faqat quyidagi JSON formatida javob qaytar, boshqa hech narsa "
                'yozma: {"summary": "xulosa matni"}'
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
