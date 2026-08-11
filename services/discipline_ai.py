"""Intizom bo'yicha AI yordamchisi: nizom raqamini bazadagi nizom bilan
solishtirib tushuntirish va apellyatsiya uchun rahbarga qaror taklifi
tayyorlash.

Haqiqiy "gate" (jarima uchun keltirilgan nizom raqami bazada mavjudmi)
doim ``services/discipline.get_rule`` orqali deterministik tekshiriladi
(``discipline_bot.py``da) — AI bu yerda faqat inson o'qishi uchun
tushuntirish/tavsiya matni qo'shadi, jarima yoki apellyatsiya oqimini
to'xtatadigan qattiq shart emas. OpenAI chaqiruvi xato bersa (tarmoq/kvota),
oddiy fallback matn bilan davom etiladi — ``main.py``dagi "AI Tahlil"
xato ushlash uslubi bilan bir xil.
"""

from openai import AsyncOpenAI

_MODEL = "gpt-5-mini"


async def confirm_rule_match(client: AsyncOpenAI, cited_text: str, rule: dict) -> str:
    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                "Sen Fokus AI intizom yordamchisisan. Nazoratchi jarima uchun "
                "keltirgan nizom bazadagi nizom matniga mos kelishini o'zbek "
                "tilida bir-ikki qisqa jumlada tasdiqla. Mos kelmasa aniq ogohlantir."
            ),
            input=(
                f"Nazoratchi yozgan matn: {cited_text!r}\n"
                f"Bazadagi {rule['rule_number']}-nizom: {rule['title']} — {rule['content']}"
            ),
        )
        return response.output_text or f"✅ {rule['rule_number']}-nizom bazada topildi: {rule['title']}"
    except Exception as error:
        print(f"OpenAI xatosi (confirm_rule_match): {error!r}")
        return f"✅ {rule['rule_number']}-nizom bazada topildi: {rule['title']}"


async def prepare_appeal_brief(
    client: AsyncOpenAI, employee_name: str, rule: dict, penalty_amount: int, reason_text: str
) -> str:
    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                "Sen Fokus AI intizom yordamchisisan. Xodimning apellyatsiyasini "
                "(dalilini) berilgan nizom va jarima bilan solishtirib, rahbar "
                "uchun o'zbek tilida qisqa va xolis qaror taklifini tayyorla. "
                "O'zing yakuniy qaror qabul qilma — faqat dalil va nizomni "
                "solishtirib, rahbarga tavsiya ber."
            ),
            input=(
                f"Xodim: {employee_name}\n"
                f"Jarima: {penalty_amount} ball, {rule['rule_number']}-nizom "
                f"({rule['title']}: {rule['content']})\n"
                f"Xodimning e'tirozi/dalili: {reason_text}"
            ),
        )
        return response.output_text or "AI tavsiya matni olinmadi."
    except Exception as error:
        print(f"OpenAI xatosi (prepare_appeal_brief): {error!r}")
        return (
            "⚠️ AI tavsiyasi olinmadi (xato) — qo'lda ko'rib chiqing.\n"
            f"Jarima: {penalty_amount} ball, {rule['rule_number']}-nizom.\n"
            f"Xodim dalili: {reason_text}"
        )
