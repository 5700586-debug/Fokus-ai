"""Ta'minotchi/haydovchi javoblarini mustaqil taqqoslash.

MUHIM: tafovut topilsa HECH QACHON avtomatik "kimdir yolg'on gapiryapti"
degan xulosa qilinmaydi. Faqat tafovut Founder/Nazoratchiga tuzilgan
holda ko'rsatiladi — aniqlashtirish ular zimmasida.
"""

from dataclasses import dataclass

from repositories import cross_check as cross_check_repo


@dataclass
class AnswerDifference:
    question: str
    answer_a: str
    answer_b: str


def start_session(session_date: str, employee_a_id: int, employee_b_id: int) -> dict:
    return cross_check_repo.get_or_create_session(session_date, employee_a_id, employee_b_id)


def record_answer(session_id: int, employee_id: int, question: str, answer: str) -> None:
    cross_check_repo.record_answer(session_id, employee_id, question, answer)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def compare_session(session_id: int, employee_a_id: int, employee_b_id: int) -> list[AnswerDifference]:
    """Bir xil savolga ikkala tomon bergan javoblarni solishtiradi.

    Faqat matn darajasida aniq mos kelmagan javoblarni "tafovut"
    sifatida qaytaradi — bu hali "yolg'on" degani emas, faqat
    aniqlashtirish kerakligi haqida signal.
    """
    answers = cross_check_repo.get_answers(session_id)

    by_employee_question: dict[tuple[int, str], str] = {}
    for row in answers:
        by_employee_question[(row["employee_id"], _normalize(row["question"]))] = row["answer"]

    questions_a = {q for (emp, q) in by_employee_question if emp == employee_a_id}
    questions_b = {q for (emp, q) in by_employee_question if emp == employee_b_id}

    differences: list[AnswerDifference] = []
    for question in questions_a & questions_b:
        answer_a = by_employee_question[(employee_a_id, question)]
        answer_b = by_employee_question[(employee_b_id, question)]
        if _normalize(answer_a) != _normalize(answer_b):
            differences.append(AnswerDifference(question=question, answer_a=answer_a, answer_b=answer_b))

    status = "discrepancy_found" if differences else "compared"
    cross_check_repo.set_status(session_id, status)

    return differences


def format_discrepancy_report(differences: list[AnswerDifference], name_a: str, name_b: str) -> str:
    if not differences:
        return "✅ Javoblarda tafovut aniqlanmadi."

    lines = ["⚠️ Javoblarda tafovut aniqlandi.", ""]
    for diff in differences:
        lines.append(f"{diff.question}")
        lines.append(f"  {name_a}: {diff.answer_a}")
        lines.append(f"  {name_b}: {diff.answer_b}")
        lines.append("")
    lines.append("Aniqlashtirish kerak.")

    return "\n".join(lines)
