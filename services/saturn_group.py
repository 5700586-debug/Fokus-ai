"""Saturn umumiy guruhidagi avtomatik postlar: ertalabki salom, kunlik
dashboard, foydali ma'lumot (tip) va kechqurungi xulosa.

Bu modul HECH QACHON ta'minotchi bilan savdolashmaydi/muzokara olib
bormaydi — faqat xodimlar uchun umumiy, bir tomonlama ma'lumot
postlari. Har bir yuborish ``services/notifications.send_once`` orqali
idempotent (bot qayta ishga tushsa ham bitta postni ikki marta
yubormaydi). Savdo raqamlari ``providers/sales_data_provider.py``dan
olinadi — ma'lumot yo'q bo'lsa raqam TO'QILMAYDI, "Ma'lumot kelmadi"
deb aniq ko'rsatiladi.
"""

import logging

from openai import AsyncOpenAI

import company_time
from providers.sales_data_provider import DailySales, get_sales_data_provider
from repositories import saturn_group as saturn_repo
from services import notifications

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"

# Mavzular: savdo madaniyati, xaridor bilan muomala, mahsulot joylash,
# tozalik, sog'lom hayot, suv ichish, to'g'ri ovqatlanish, jismoniy
# faollik, uyqu va gigiyena — talab qilingan ro'yxat bo'yicha.
_TIP_BANK: list[tuple[str, str]] = [
    ("savdo_1", "Xaridor do'konga kirganda 5 soniya ichida salomlashish sotuvni 20% gacha oshirishi mumkin — birinchi taassurot muhim."),
    ("savdo_2", "Xaridorni tinglang, gapini bo'lmang — u nima izlayotganini aniq bilib, keyin taklif bering."),
    ("muomala_1", "Xaridor bilan janjal chiqsa, ovozingizni ko'tarmang — xotirjam tinglang va yechim taklif qiling."),
    ("muomala_2", "Xaridorga ismi bilan murojaat qilish (agar bilsangiz) ishonchni oshiradi."),
    ("joylash_1", "Ko'p sotiladigan mahsulotlarni ko'z balandligida joylashtiring — bu tasodifiy xarid ehtimolini oshiradi."),
    ("joylash_2", "Chang bosgan yoki muddati o'tayotgan mahsulotni har kuni tekshiring — bu ishonchni yo'qotadi."),
    ("tozalik_1", "Toza vitrina va tartibli javon — xaridor ko'zi bilan birinchi baholaydigan narsa."),
    ("tozalik_2", "Ish joyingizni smena boshida va oxirida tekshirib chiqing — kichik tartibsizlik katta taassurot qoldiradi."),
    ("salomatlik_suv", "Kuniga kamida 8 stakan suv iching — chanqoqlik his qilguningizcha kutmang, diqqatingiz susayadi."),
    ("salomatlik_ovqat", "Ish orasida yengil va muntazam ovqatlaning — och qoringa uzoq ishlash xatolarni ko'paytiradi."),
    ("salomatlik_harakat", "Har 1-2 soatda 2-3 daqiqa turib, cho'zilib oling — uzoq o'tirish/turish charchoqni kuchaytiradi."),
    ("salomatlik_uyqu", "Kamida 7 soat uxlang — yetarli uyqu diqqat va xushmuomalalikni saqlab turadi."),
    ("gigiyena_1", "Ish joyida va mahsulot bilan ishlaganda qo'l gigiyenasiga alohida e'tibor bering."),
    ("jamoaviylik_1", "Hamkasbingizga yordam qo'lini cho'zish jamoa ruhini mustahkamlaydi — bugun kimgadir yordam bering."),
    ("savdo_3", "Xaridorga faqat kerakli mahsulotni emas, unga mos qo'shimcha mahsulotni ham taklif qiling — bu ham xaridorga, ham savdoga foyda."),
    ("muomala_3", "Norozi xaridorni tezda ayblab yoki oqlab qo'ymang — avval uni to'liq tinglang."),
]


def _tz_now():
    return company_time.now()


def _today_str() -> str:
    return company_time.today().isoformat()


def _pick_tip() -> tuple[str, str]:
    recent_keys = set(saturn_repo.get_recent_tip_keys(limit=7))
    for key, text in _TIP_BANK:
        if key not in recent_keys:
            return key, text
    return _TIP_BANK[0]


async def _ai_text(client: AsyncOpenAI, instructions: str, prompt: str, fallback: str) -> str:
    try:
        response = await client.responses.create(model=_MODEL, instructions=instructions, input=prompt)
        return response.output_text or fallback
    except Exception as error:
        logger.warning("OpenAI xatosi (saturn_group): %r", error)
        return fallback


async def build_morning_message(client: AsyncOpenAI) -> str:
    recent = [p["content"] for p in saturn_repo.get_recent_posts("morning", limit=7)]
    recent_block = "\n---\n".join(recent) if recent else "(hali post bo'lmagan)"

    return await _ai_text(
        client,
        instructions=(
            "Sen Saturn kompaniyasining Fokus AI yordamchisisan. Xodimlar uchun "
            "Telegram guruhiga ertalabki 'Xayrli tong, Saturn jamoasi' xabarini "
            "o'zbek tilida yoz: chiroyli, qisqa, samimiy va ilhomlantiruvchi. "
            "Quyidagi 'Oldingi xabarlar' ro'yxatidagi matnlarni AYNAN takrorlama — "
            "har safar boshqacha so'z va uslub bilan yoz. Raqam yoki statistika "
            "to'qima — bu faqat kayfiyat ko'taruvchi matn."
        ),
        prompt=f"Oldingi xabarlar (buni takrorlama):\n{recent_block}",
        fallback="🌅 Xayrli tong, Saturn jamoasi! Bugun ham kuchli va hamjihat ishlaymiz. 💪",
    )


def _fmt_amount(value: float | None) -> str:
    if value is None:
        return "Ma'lumot kelmadi"
    return f"{value:,.0f}".replace(",", " ")


def _fmt_count(value: int | None) -> str:
    return "Ma'lumot kelmadi" if value is None else str(value)


def _fmt_pct(value: float | None) -> str:
    return "Ma'lumot kelmadi" if value is None else f"{value:.1f}%"


def render_dashboard_numbers(sales: DailySales) -> str:
    completion_pct = None
    if sales.plan_amount and sales.actual_amount is not None:
        completion_pct = (sales.actual_amount / sales.plan_amount) * 100

    avg_check = None
    if sales.actual_amount is not None and sales.receipt_count:
        avg_check = sales.actual_amount / sales.receipt_count

    vs_yesterday = None
    if sales.actual_amount is not None and sales.yesterday_actual_amount is not None:
        vs_yesterday = sales.actual_amount - sales.yesterday_actual_amount

    remaining = None
    if sales.plan_amount is not None and sales.actual_amount is not None:
        remaining = sales.plan_amount - sales.actual_amount

    lines = [
        f"📅 Kunlik reja: {_fmt_amount(sales.plan_amount)}",
        f"💰 Haqiqiy savdo: {_fmt_amount(sales.actual_amount)}",
        f"📈 Bajarilish foizi: {_fmt_pct(completion_pct)}",
        f"🧾 Cheklar soni: {_fmt_count(sales.receipt_count)}",
        f"🧮 O'rtacha chek: {_fmt_amount(avg_check)}",
        f"📊 Kechagi savdoga nisbatan: {_fmt_amount(vs_yesterday)}",
        f"⏳ Qolgan reja: {_fmt_amount(remaining)}",
    ]
    return "\n".join(lines)


async def build_dashboard_message(client: AsyncOpenAI, sales: DailySales) -> str:
    numbers_block = render_dashboard_numbers(sales)
    has_any_data = any(
        v is not None
        for v in (sales.plan_amount, sales.actual_amount, sales.receipt_count, sales.yesterday_actual_amount)
    )

    analysis = await _ai_text(
        client,
        instructions=(
            "Sen Saturn kompaniyasining Fokus AI tahlilchisisan. Berilgan kunlik "
            "savdo raqamlari asosida o'zbek tilida 2-3 jumlali QISQA tahlil va "
            "amaliy tavsiya yoz. Raqamlar 'Ma'lumot kelmadi' bo'lsa, HECH QACHON "
            "raqam to'qima — shunchaki ma'lumot yo'qligini qisqa aytib, umumiy "
            "foydali tavsiya ber (masalan diqqat/xizmat sifatiga)."
        ),
        prompt=f"Bugungi raqamlar:\n{numbers_block}",
        fallback=(
            "Bugungi savdo ma'lumotlari hali kelmadi — diqqatni xizmat sifati va "
            "xaridor bilan ishlashga qarating."
            if not has_any_data
            else "Raqamlarga qarab, bugungi tezlikni ushlab turishga harakat qiling."
        ),
    )

    return f"📊 Bugungi dashboard\n\n{numbers_block}\n\n🤖 {analysis}"


async def build_evening_message(client: AsyncOpenAI, sales: DailySales) -> str:
    numbers_block = render_dashboard_numbers(sales)

    closing = await _ai_text(
        client,
        instructions=(
            "Sen Saturn kompaniyasining Fokus AI yordamchisisan. Kun yakunida "
            "xodimlar uchun 'Xayrli tun, Saturn jamoasi' xabarini o'zbek tilida "
            "yoz: kun natijasini xotirjam sharhla. Agar reja bajarilgan/yaxshi "
            "bo'lsa, buni e'tirof et va rahmat ayt. Agar kamchilik bo'lsa, HECH "
            "KIMNI ayblama — ayblamasdan, ertangi kun uchun aniq va ijobiy "
            "tavsiya ber. Raqamlar 'Ma'lumot kelmadi' bo'lsa, to'qima."
        ),
        prompt=f"Bugungi yakuniy raqamlar:\n{numbers_block}",
        fallback="🌙 Xayrli tun, Saturn jamoasi! Bugungi mehnatingiz uchun rahmat, ertaga yana kuchliroq davom etamiz.",
    )

    return f"🌙 Kun yakuni\n\n{numbers_block}\n\n{closing}"


async def send_morning_message(bot, client: AsyncOpenAI, group_chat_id: int) -> None:
    today = _today_str()
    text = await build_morning_message(client)
    sent = await notifications.send_once(bot, f"saturn_morning_{today}", group_chat_id, text)
    if sent:
        saturn_repo.log_post("morning", today, text)


async def send_dashboard_message(bot, client: AsyncOpenAI, group_chat_id: int, slot_label: str) -> None:
    today = _today_str()
    provider = get_sales_data_provider()
    sales = await provider.get_daily_sales(today)
    text = await build_dashboard_message(client, sales)
    sent = await notifications.send_once(bot, f"saturn_dashboard_{today}_{slot_label}", group_chat_id, text)
    if sent:
        saturn_repo.log_post("dashboard", today, text)


async def send_evening_message(bot, client: AsyncOpenAI, group_chat_id: int) -> None:
    today = _today_str()
    provider = get_sales_data_provider()
    sales = await provider.get_daily_sales(today)
    text = await build_evening_message(client, sales)
    sent = await notifications.send_once(bot, f"saturn_evening_{today}", group_chat_id, text)
    if sent:
        saturn_repo.log_post("evening", today, text)


async def send_tip_message(bot, group_chat_id: int) -> None:
    today = _today_str()
    tip_key, tip_text = _pick_tip()
    text = f"💡 Foydali ma'lumot\n\n{tip_text}"
    sent = await notifications.send_once(bot, f"saturn_tip_{today}", group_chat_id, text)
    if sent:
        saturn_repo.log_post("tip", today, text, tip_key=tip_key)
