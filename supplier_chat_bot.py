"""Ta'minotchi (tashqi hamkor) bilan shaxsiy chatdagi bot qatlami.

Faqat Telegram marshrutlash/klaviatura — hisob-kitob va AI chaqiruvi
``services/supplier_ai.py``da. Bu handlerlar FAQAT shaxsiy chatda
(``chat.type == "private"``) va faqat ro'yxatdan o'tgan xodim
BO'LMAGAN (``roles.is_authorized`` — False) foydalanuvchilar uchun
ishlaydi, shuning uchun Saturn umumiy guruhida yoki xodimlar bilan
hech qachon aralashmaydi.
"""

import logging

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from openai import AsyncOpenAI

from config import FOUNDER_ID
from repositories import suppliers as suppliers_repo
from roles import is_authorized
from services import supplier_ai

logger = logging.getLogger(__name__)


async def is_supplier_text(message: Message) -> bool:
    """Faqat shaxsiy chatda, xodim BO'LMAGAN va ro'yxatdan o'tgan
    ta'minotchi yuborgan erkin matn uchun ``True``. Guruh xabarlari
    (``chat.type != "private"``) hech qachon mos kelmaydi — bot Saturn
    umumiy guruhida ta'minotchi bilan hech qachon savdolashmaydi.
    """
    if message.chat.type != "private":
        return False
    if not message.text or message.text.startswith("/"):
        return False
    if not message.from_user:
        return False
    if is_authorized(message.from_user.id):
        return False
    return suppliers_repo.get_supplier_by_telegram_id(message.from_user.id) is not None


async def try_claim_invite(message: Message, token: str) -> bool:
    """``main.py``dagi ``/start <token>`` handleri chaqiradi. Token
    ta'minotchi taklifi bo'lsa suhbatni boshlab ``True`` qaytaradi,
    aks holda ``False`` (chaqiruvchi keyin xodim taklifini tekshiradi).
    """
    if not message.from_user:
        return False

    existing = suppliers_repo.get_supplier_by_telegram_id(message.from_user.id)
    if existing is not None:
        await message.answer(
            "Assalomu alaykum! Siz allaqachon ro'yxatdan o'tgansiz — "
            "xabaringizni shu yerga yozishingiz mumkin."
        )
        return True

    supplier = suppliers_repo.claim_invite(token, message.from_user.id)
    if supplier is None:
        return False

    await message.answer(
        "Assalomu alaykum! 👋 Men Saturn kompaniyasining Fokus AI yordamchisiman.\n\n"
        "Siz bilan hamkorlik imkoniyatlarini muhokama qilish uchun bir nechta savol "
        "beraman — korxonangiz, mahsulotlaringiz va yetkazib berish shartlaringiz haqida.\n\n"
        "Boshlash uchun: korxonangiz nomi va qaysi hududda faoliyat yuritishingizni yozib bering."
    )
    return True


def register(dp: Dispatcher, openai_client: AsyncOpenAI) -> None:
    @dp.message(Command("invitesupplier"))
    async def invite_supplier_handler(message: Message) -> None:
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        parts = (message.text or "").split(maxsplit=1)
        company_hint = parts[1].strip() if len(parts) > 1 else None

        token = suppliers_repo.create_invite(company_hint, created_by=FOUNDER_ID)
        me = await message.bot.get_me()
        link = f"https://t.me/{me.username}?start={token}"

        await message.answer(
            "✅ Ta'minotchi uchun shaxsiy taklif havolasi yaratildi "
            f"({suppliers_repo.INVITE_TTL_HOURS} soat amal qiladi):\n{link}\n\n"
            "Bu havolani ta'minotchiga to'g'ridan-to'g'ri yuboring — bosganda bot bilan "
            "shaxsiy chatda AI suhbati boshlanadi (Saturn umumiy guruhida emas)."
        )

    @dp.message(Command("supplierlist"))
    async def supplier_list_handler(message: Message) -> None:
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        active = suppliers_repo.list_suppliers("active")
        if not active:
            await message.answer("Hozircha ro'yxatga olingan ta'minotchi yo'q.")
            return

        lines = "\n".join(
            f"#{s['id']} — {s['company_name'] or 'nomaʼlum kompaniya'} "
            f"({s['region'] or 'hudud nomaʼlum'})"
            for s in active
        )
        await message.answer(f"Faol ta'minotchilar:\n{lines}")

    @dp.message(Command("supplierreport"))
    async def supplier_report_handler(message: Message) -> None:
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await message.answer("Foydalanish: /supplierreport <ta'minotchi_id>")
            return

        supplier_id = int(parts[1].strip())
        supplier = suppliers_repo.get_supplier(supplier_id)
        if supplier is None:
            await message.answer(f"❌ #{supplier_id} ta'minotchi topilmadi.")
            return

        waiting = await message.answer("⏳ Xulosa tayyorlanyapti...")
        summary = await supplier_ai.generate_founder_summary(openai_client, supplier)
        await waiting.edit_text(
            f"📋 Ta'minotchi xulosasi — {supplier.get('company_name') or supplier_id}:\n\n{summary}"
        )

    @dp.message(Command("supplierscompare"))
    async def supplier_compare_handler(message: Message) -> None:
        if not message.from_user or message.from_user.id != FOUNDER_ID:
            return

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.answer("Foydalanish: /supplierscompare <mahsulot nomi>")
            return

        product_name = parts[1].strip()
        data = supplier_ai.compare_offers_for_product(product_name)

        offer_lines = "\n".join(
            f"- {o.get('supplier_company_name') or o['supplier_id']}: narx={o.get('price')}, "
            f"chegirma={o.get('discount')}, min_buyurtma={o.get('minimum_order')}"
            for o in data["supplier_offers"]
        ) or "(hali taklif yo'q)"

        market_lines = "\n".join(
            f"- {m['observation_date']}: {m.get('wholesale_price')} "
            f"({m.get('supplier_seller') or 'nomaʼlum'})"
            for m in data["market_reference"]
        ) or "(bozor kuzatuvi topilmadi)"

        await message.answer(
            f"📊 {product_name} — ta'minotchilar taklifi:\n{offer_lines}\n\n"
            f"Bozor razvedkasi (/marketlog tarixi):\n{market_lines}"
        )

    @dp.message(F.text, is_supplier_text)
    async def supplier_text_handler(message: Message) -> None:
        supplier = suppliers_repo.get_supplier_by_telegram_id(message.from_user.id)
        if supplier is None or supplier["status"] != "active":
            return

        waiting = await message.answer("⏳ ...")
        try:
            reply = await supplier_ai.handle_supplier_message(openai_client, supplier, message.text)
        except Exception as error:
            logger.warning("Ta'minotchi xabarini qayta ishlashda xato: %r", error)
            await waiting.edit_text(
                "Kechirasiz, texnik xatolik yuz berdi. Xabaringizni qayta yuboring."
            )
            return

        await waiting.edit_text(reply)
