"""Intizom bo'yicha AI yordamchisi: nizom raqamini bazadagi nizom bilan
solishtirib tushuntirish va apellyatsiya uchun rahbarga qaror taklifi
tayyorlash.

Haqiqiy "gate" (jarima uchun keltirilgan nizom raqami bazada mavjudmi)
doim ``services/discipline.get_rule`` orqali deterministik tekshiriladi
(``discipline_bot.py``da) — AI bu yerda faqat inson o'qishi uchun
tushuntirish/tavsiya matni qo'shadi, jarima yoki apellyatsiya oqimini
to'xtatadigan qattiq shart emas. OpenAI chaqiruvi xato bersa (tarmoq/kvota),
oddiy fallback matn bilan davom etiladi — botni yiqitmaydigan try/except
uslubida.
"""

import re

from openai import AsyncOpenAI

_MODEL = "gpt-5-mini"
_BARE_NUMBER_RE = re.compile(r"^\s*(\d+)\s*$")


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


async def match_incident_to_rule(client: AsyncOpenAI, incident_text: str, rules: list[dict]) -> int | None:
    """Nazoratchi "📝 Boshqa holat" orqali yozgan erkin matnni
    TASDIQLANGAN (ball miqdori belgilangan) nizom bandlari bilan
    MAZMUNAN solishtiradi — so'zma-so'z bir xil bo'lishi shart emas.

    Haqiqiy "gate" shu yerda ham deterministik: AI faqat MAVJUD
    ro'yxatdagi bitta band raqamini (yoki hech biri mos kelmasa
    ``None``) tanlaydi — yangi jazo yoki miqdorni O'ZI o'ylab
    TOPMAYDI, chaqiruvchi kod (``nazoratchi_bot.py``) yakuniy
    qo'llashdan oldin Nazoratchiga albatta tasdiqlatadi. AI
    javobi ro'yxatdagi HAQIQIY raqamlardan biriga aynan mos
    kelmasa (parsing xatosi, ishlab chiqarilgan/mavjud bo'lmagan
    raqam va h.k.) yoki OpenAI chaqiruvi xato bersa — ``None``
    (mos kelmadi) qaytariladi, hech qachon taxmin qilinmaydi."""
    if not rules:
        return None

    catalog = "\n".join(f"{rule['rule_number']}: {rule['title']} — {rule['content']}" for rule in rules)
    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                "Sen Fokus AI intizom yordamchisisan. Nazoratchi yozgan holat "
                "matnini quyidagi TASDIQLANGAN nizom bandlari ro'yxati bilan "
                "MAZMUNAN solishtir (so'zma-so'z bir xil bo'lishi shart emas). "
                "Agar holat aniq bir bandga mos kelsa, FAQAT o'sha bandning "
                "raqamini son sifatida javob ber (masalan: 3). Agar hech qanday "
                "band aniq mos kelmasa yoki ikkilanarli bo'lsa, FAQAT 'YOQ' deb "
                "javob ber. Boshqa hech qanday matn yozma — yangi band yoki "
                "miqdor o'ylab topma."
            ),
            input=f"Nizom bandlari:\n{catalog}\n\nNazoratchi yozgan holat: {incident_text!r}",
        )
        raw = response.output_text or ""
    except Exception as error:
        print(f"OpenAI xatosi (match_incident_to_rule): {error!r}")
        return None

    match = _BARE_NUMBER_RE.match(raw)
    if not match:
        return None

    rule_number = int(match.group(1))
    if any(rule["rule_number"] == rule_number for rule in rules):
        return rule_number
    return None


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
