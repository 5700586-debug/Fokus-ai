"""Ta'minotchi (tashqi hamkor) bilan shaxsiy chatdagi AI suhbat.

Bitta OpenAI chaqiruvi navbat bo'yicha ikkita narsani qaytaradi: (1)
ta'minotchiga yuboriladigan tabiiy javob matni, (2) shu xabarda aniq
aytilgan struktura maydonlar (mahsulot/narx/shart/profil). AI hech
qachon aytilmagan maydonni to'qib chiqarmaydi — faqat ta'minotchi
o'zi aniq aytgan narsa ``supplier_offers``/``suppliers``ga yoziladi.

**Maxfiylik:** bu modul hech qachon boshqa ta'minotchining ma'lumotini
(narx, shart, suhbat) joriy ta'minotchiga yuboriladigan promptga
qo'shmaydi — faqat shu ta'minotchining o'z tarixi/profili beriladi,
shuning uchun AI modelning o'zi xato qilsa ham oshkor qiladigan
narsa yo'q. Ta'minotchilar orasidagi taqqoslash faqat
``compare_offers_for_product``/``generate_founder_summary`` orqali va
faqat Founder'ga yuboriladi.

Narx/hamkorlik bo'yicha yakuniy qarorni AI hech qachon qabul qilmaydi —
faqat Founder uchun tahlil/tavsiya matni tayyorlaydi (loyihadagi
``discipline_ai.py`` bilan bir xil tamoyil).
"""

import json
import logging

from openai import AsyncOpenAI

from repositories import market as market_repo
from repositories import suppliers as suppliers_repo

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"

_FALLBACK_REPLY = (
    "Kechirasiz, hozir javobni tayyorlashda texnik xatolik yuz berdi. "
    "Iltimos, xabaringizni birozdan so'ng qayta yuboring."
)

_CONVERSATION_INSTRUCTIONS = """Sen Saturn kompaniyasi nomidan tashqi ta'minotchilar bilan
shaxsiy Telegram chatda muloqot qiluvchi Fokus AI yordamchisisan.

Vazifang:
- Ta'minotchining korxonasi, mahsulotlari, hududi, yetkazish imkoniyati va
  shartlarini tabiiy suhbat orqali o'rgan.
- Mahsulot nomi, narxi, chegirmasi, minimal buyurtma, yetkazish muddati,
  to'lov turi va qaytarish shartlarini tartibli yig'.
- Suhbatni iliq, samimiy va professional olib bor, o'zbek tilida yoz.
- "Oxirgi suhbat" ro'yxatidagi savollarni TAKRORLAMA — agar bir narsa
  allaqachon so'ralgan/aytilgan bo'lsa, boshqa mavzuga o't yoki
  yetishmayotgan ma'lumotni so'ra.
- Hech qachon ma'lumotni o'zing to'qima. Yetishmagan ma'lumotni ta'minotchidan so'ra.
- Narx yoki hamkorlik bo'yicha yakuniy qarorni SEN qabul qilmaysan va bunday
  va'da bermaysan — bu qaror doim Asoschida ekanini bilib qo'y (lekin buni
  har safar ta'minotchiga aytib o'tirma, faqat so'ralsa tushuntir).
- Boshqa ta'minotchilar yoki Saturnning ichki maxfiy ma'lumotlarini hech
  qachon oshkor qilma (senga ular berilmaydi ham).

Javobingni FAQAT quyidagi JSON formatida qaytar (boshqa matn yozma):
{
  "reply": "ta'minotchiga yuboriladigan matn",
  "company_name": null yoki matn (agar shu xabarda aniq aytilgan bo'lsa),
  "region": null yoki matn,
  "contact_name": null yoki matn,
  "phone": null yoki matn,
  "product_name": null yoki matn (agar mahsulot haqida gap ketsa),
  "price": null yoki matn,
  "discount": null yoki matn,
  "minimum_order": null yoki matn,
  "delivery_time": null yoki matn,
  "payment_type": null yoki matn,
  "return_terms": null yoki matn
}
Faqat shu xabarda ANIQ aytilgan maydonlarni to'ldir, qolganini null qoldir."""


def _parse_ai_json(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text)


async def handle_supplier_message(client: AsyncOpenAI, supplier: dict, incoming_text: str) -> str:
    supplier_id = supplier["id"]
    suppliers_repo.add_message(supplier_id, "user", incoming_text)

    history = suppliers_repo.get_recent_messages(supplier_id, limit=20)
    history_lines = "\n".join(f"{m['role']}: {m['content']}" for m in history)

    profile_lines = "\n".join(
        f"{key}: {supplier.get(key) or 'nomaʼlum'}"
        for key in ("company_name", "region", "contact_name", "phone")
    )

    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=_CONVERSATION_INSTRUCTIONS,
            input=(
                f"Ta'minotchi profili (hozirgacha ma'lum):\n{profile_lines}\n\n"
                f"Oxirgi suhbat (eski -> yangi):\n{history_lines}\n\n"
                f"Ta'minotchining yangi xabari: {incoming_text!r}"
            ),
        )
        data = _parse_ai_json(response.output_text)
        reply = data.get("reply") or _FALLBACK_REPLY
    except Exception as error:
        logger.warning("OpenAI xatosi (handle_supplier_message): %r", error)
        suppliers_repo.add_message(supplier_id, "assistant", _FALLBACK_REPLY)
        return _FALLBACK_REPLY

    profile_updates = {
        key: data.get(key)
        for key in ("company_name", "region", "contact_name", "phone")
        if data.get(key)
    }
    if profile_updates:
        suppliers_repo.update_supplier_profile(supplier_id, **profile_updates)

    product_name = data.get("product_name")
    if product_name:
        offer_updates = {
            key: data.get(key)
            for key in (
                "price",
                "discount",
                "minimum_order",
                "delivery_time",
                "payment_type",
                "return_terms",
            )
            if data.get(key)
        }
        if offer_updates:
            suppliers_repo.upsert_offer(supplier_id, product_name, **offer_updates)

    suppliers_repo.add_message(supplier_id, "assistant", reply)
    return reply


def compare_offers_for_product(product_name: str) -> dict:
    """Founder-only: shu mahsulot bo'yicha barcha ta'minotchilar
    takliflari + bozor razvedkasi (``/marketlog``) narx tarixi."""
    return {
        "supplier_offers": suppliers_repo.list_offers_for_product(product_name),
        "market_reference": market_repo.get_price_history(product_name),
    }


async def generate_founder_summary(client: AsyncOpenAI, supplier: dict) -> str:
    supplier_id = supplier["id"]
    offers = suppliers_repo.list_offers(supplier_id)
    history = suppliers_repo.get_recent_messages(supplier_id, limit=30)

    offers_lines = "\n".join(
        f"- {o['product_name']}: narx={o.get('price')}, chegirma={o.get('discount')}, "
        f"min_buyurtma={o.get('minimum_order')}, yetkazish={o.get('delivery_time')}, "
        f"to'lov={o.get('payment_type')}, qaytarish={o.get('return_terms')}"
        for o in offers
    ) or "(hali mahsulot ma'lumoti yig'ilmagan)"

    history_lines = "\n".join(f"{m['role']}: {m['content']}" for m in history)

    fallback = (
        f"⚠️ AI xulosasi tayyorlanmadi (texnik xato) — qo'lda ko'rib chiqing.\n"
        f"Ta'minotchi: {supplier.get('company_name') or supplier_id}\n"
        f"Ma'lum takliflar:\n{offers_lines}"
    )

    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                "Sen Fokus AI tahlilchisisan. Berilgan ta'minotchi bilan suhbat "
                "tarixi va takliflari asosida Asoschiga (Founder) o'zbek tilida "
                "qisqa xulosa tayyorla: ta'minotchi qanday, takliflari bozorga "
                "nisbatan qanday, qaysi mahsulotlar Saturn uchun foydali bo'lishi "
                "mumkin, qimmat/xavfli/foydasiz taklif bormi, va aniq tavsiya. "
                "Yakuniy narx/hamkorlik qarorini SEN qabul qilma — faqat tahlil "
                "va tavsiya ber, qaror doim Asoschida."
            ),
            input=(
                f"Ta'minotchi: {supplier.get('company_name') or 'nomasum'} "
                f"(hudud: {supplier.get('region') or 'nomalum'})\n\n"
                f"Takliflar:\n{offers_lines}\n\n"
                f"Suhbat tarixi:\n{history_lines}"
            ),
        )
        summary = response.output_text or fallback
    except Exception as error:
        logger.warning("OpenAI xatosi (generate_founder_summary): %r", error)
        summary = fallback

    suppliers_repo.add_founder_summary(supplier_id, summary)
    return summary
