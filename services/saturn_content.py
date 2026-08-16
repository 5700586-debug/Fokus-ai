"""Saturn tonggi/tungi rasmli xabari uchun qisqa foydali maslahat matni.

Ikki mustaqil, qo'lda tekshirilgan bank: tonggi (operatsion — xizmat,
muomala, tozalik, jamoaviylik, diqqat, rivojlanish, sog'liq) va tungi
(kun yakuni — dam olish, minnatdorchilik, ertangi kunga tayyorgarlik).
Ikkalasi ham tibbiy/huquqiy/siyosiy/bahsli mazmundan XOLI — har bir
matn qo'lda yozilgan va tekshirilgan (AI tomonidan TO'QILMAGAN).

AI (mavjud bo'lsa) faqat TANLANGAN bank matnini boshqacha so'z bilan
qayta ifodalash uchun ishlatiladi — yangi mavzu o'ylab topmaydi, faqat
bor matnni "yangilaydi". Natija uzunlik va bo'shlik bo'yicha tekshiriladi
— mos kelmasa yoki AI ishlamasa, original bank matni o'zgarishsiz
ishlatiladi (xabar yuborish hech qachon to'xtamaydi).

Oxirgi 30 kunda (aniqrog'i — oxirgi 30 ta shu turdagi post) ishlatilgan
mavzu qayta tanlanmaydi (``repositories/saturn_group.get_recent_content_keys``).
"""

import logging

from openai import AsyncOpenAI

from repositories import saturn_group as saturn_repo

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"
_MAX_ADVICE_LENGTH = 130  # 120 belgilik maqsaddan biroz xavfsizlik zaxirasi bilan

# ------------------------------------------------------------- tonggi bank --
# Mavzular: savdo/xizmat, muomala, tozalik/tartib, mahsulot joylash,
# jamoaviylik, diqqat, rivojlanish, ishni yengillashtirish, sog'liq.
MORNING_ADVICE_BANK: list[tuple[str, str]] = [
    ("m_sav_1", "Xaridor eshikdan kirgan zahoti tabassum bilan salomlashing — birinchi taassurot doim yodda qoladi."),
    ("m_sav_2", "Xaridorni tinglang, gapini bo'lmang — nima izlayotganini aniq bilib, keyin taklif bering."),
    ("m_sav_3", "Xaridorga faqat kerakli emas, mos qo'shimcha mahsulotni ham taklif qiling — ikkalasiga foyda."),
    ("m_sav_4", "Savol beruvchi xaridorni hech qachon shoshiltirmang — sabr ishonchni mustahkamlaydi."),
    ("m_sav_5", "Kassada navbat uzayganda ham xotirjamlikni saqlang — shoshilish xato qildiradi."),
    ("m_sav_6", "Mahsulot haqida savol bersa, bilmagan narsangizni yashirmang — so'rab, keyin aniq javob bering."),
    ("m_muo_1", "Norozi xaridorni ayblab yoki oqlab qo'ymang — avval to'liq tinglang, keyin yechim toping."),
    ("m_muo_2", "Xaridorga ismi bilan murojaat qilish (bilsangiz) ishonchni sezilarli oshiradi."),
    ("m_muo_3", "Janjal chiqsa, ovozingizni ko'tarmang — xotirjamlik eng kuchli javobdir."),
    ("m_muo_4", "Kimningdir kayfiyati yomon bo'lsa, buni shaxsiy qabul qilmang — samimiy muomala saqlang."),
    ("m_muo_5", "Xaridorga yolg'on va'da bermang — mahsulot haqida faqat aniq bilganingizni ayting."),
    ("m_muo_6", "Kutish vaqti uzunroq bo'lsa, xaridorga buni bildirib qo'ying — noaniqlik norozilik keltiradi."),
    ("m_toz_1", "Toza vitrina va tartibli javon — xaridor birinchi ko'radigan va baholaydigan narsa."),
    ("m_toz_2", "Smena boshida va oxirida ish joyingizni tekshirib chiqing — kichik tartib katta taassurot beradi."),
    ("m_toz_3", "Chang bosgan yoki muddati o'tgan mahsulotni har kuni tekshiring — bu ishonchni saqlaydi."),
    ("m_toz_4", "Ish kiyimingiz va tashqi ko'rinishingiz ham xaridor uchun kompaniyaning vizitkasidir."),
    ("m_joy_1", "Ko'p sotiladigan mahsulotni ko'z balandligida joylashtiring — bu tasodifiy xaridni oshiradi."),
    ("m_jam_1", "Hamkasbingizga yordam qo'lini cho'zing — jamoa ruhi kichik yordamlardan mustahkamlanadi."),
    ("m_jam_2", "Bugun kimgadir rahmat ayting — kichik minnatdorchilik kayfiyatni butun kunga yaxshilaydi."),
    ("m_jam_3", "Yangi hamkasbingizga savol berishdan tortinmang — birga ishlash tezroq o'rgatadi."),
    ("m_jam_4", "Rahbaringiz yoki hamkasbingiz fikr bildirsa, uni tinglang — bu sizning o'sishingizga yordam beradi."),
    ("m_diq_1", "Ishni boshlashdan oldin bugungi asosiy 3 vazifangizni aniqlab oling — diqqat tarqalmaydi."),
    ("m_diq_2", "Telefon bilan ovora bo'lib, xaridorni ko'zdan qochirmang — u sizni kuzatayotganini unutmang."),
    ("m_diq_3", "Bugun bironta ishni \"keyinroq\" demasdan, darhol bajarib qo'yishga harakat qiling."),
    ("m_riv_1", "Har kuni bitta yangi narsa o'rganishga harakat qiling — kichik qadamlar katta natija beradi."),
    ("m_riv_2", "Xato qilsangiz, uni yashirmang — tan olish va tuzatish rivojlanishning eng qisqa yo'li."),
    ("m_riv_3", "Kichik muvaffaqiyatlaringizni ham qadrlang — ular katta natijaning bir qismi."),
    ("m_yen_1", "Ish boshida kerakli buyum va hujjatlarni tayyorlab qo'ying — kun davomida vaqt tejaydi."),
    ("m_yen_2", "Takrorlanadigan ishni soddalashtirish yo'lini toping — kichik o'zgarish ko'p vaqt tejaydi."),
    ("m_vaq_1", "Kun boshida rejani tuzib oling — nima qachon bajarilishini bilish tashvishni kamaytiradi."),
    ("m_sal_1", "Kuniga yetarlicha suv iching — chanqoqlik sezguningizcha kutmang, diqqat susayadi."),
    ("m_sal_2", "Ish orasida yengil va o'z vaqtida ovqatlaning — och qorin xatolarni ko'paytiradi."),
    ("m_sal_3", "Har 1-2 soatda 2-3 daqiqa turib cho'zilib oling — uzoq bir holatda turish charchoqni oshiradi."),
    ("m_sal_4", "Yetarli uxlash diqqat va xushmuomalalikni saqlaydi — bugun ertaroq yotishga harakat qiling."),
    ("m_gig_1", "Mahsulot va pul bilan ishlaganda qo'l gigiyenasiga alohida e'tibor bering."),
]

# -------------------------------------------------------------- tungi bank --
# Mavzular: dam olish, minnatdorchilik, ertangi kunga tayyorgarlik,
# ish joyini tartibga solish, ijobiy fikrlash, uyqu.
NIGHT_ADVICE_BANK: list[tuple[str, str]] = [
    ("n_tartib_1", "Ish joyini tartibli qoldirish — ertangi kunni yengil boshlash demakdir."),
    ("n_minnat_1", "Bugun qilgan mehnatingiz uchun o'zingizga rahmat ayting — har kun qadr-qimmatga loyiq."),
    ("n_tayyor_1", "Ertangi kun uchun ustuvor bitta vazifani bugunoq belgilab qo'ying."),
    ("n_uyqu_1", "Uxlashdan oldin telefonni chetga qo'ying — sifatli dam olish ertangi kunni yengillashtiradi."),
    ("n_oila_1", "Uyga qaytganingizda oilangiz bilan bugungi kun haqida gaplashib, ulushib oling."),
    ("n_ijobiy_1", "Bugun nima yaxshi ketgani haqida bir daqiqa o'ylab ko'ring — kichik yutuqlar ham muhim."),
    ("n_tartib_2", "Ertaga kerak bo'ladigan narsalarni bugun kechqurun tayyorlab qo'yish vaqtni tejaydi."),
    ("n_dam_1", "Ish va dam olish orasida chegara qo'ying — ertangi kuchingiz shu dam olishga bog'liq."),
    ("n_minnat_2", "Bugun sizga yordam bergan hamkasbingizga xabar yozib, rahmat ayting."),
    ("n_ijobiy_2", "Kamchilikka emas, ertangi imkoniyatga e'tibor qarating — har kun yangi boshlanish."),
    ("n_uyqu_2", "Erta yotish — ertangi kunni yangi kuch bilan boshlashning eng oddiy yo'li."),
    ("n_tayyor_2", "Ertangi rejangizni ko'zdan kechiring — noaniqlik kamaysa, tinch uxlaysiz."),
    ("n_oila_2", "Kichik bo'lsa ham, sevganlaringiz bilan birga o'tkazgan daqiqalar eng qimmatli."),
    ("n_dam_2", "Bugun charchagan bo'lsangiz, bu tabiiy — ertaga dam olib, yangi kuch bilan kelasiz."),
    ("n_tartib_3", "Kunlik ro'yxatingizni tekshirib, bajarilganini belgilang — bu tinchlik his qildiradi."),
    ("n_ijobiy_3", "Har kun mukammal bo'lishi shart emas — muhimi, harakat qilishda davom etish."),
    ("n_minnat_3", "Bugun sizga tabassum ulashgan xaridorni eslang — yaxshilik yaxshilikni tug'diradi."),
    ("n_dam_3", "Uyqudan oldin bugungi tashvishlarni qog'ozga yozib qo'yish ongni tinchlantiradi."),
    ("n_tayyor_3", "Ertangi kiyim va buyumlaringizni oldindan tayyorlab qo'ying — tong shoshilinch o'tmaydi."),
    ("n_oila_3", "Uyga yetib borganingizda, bir daqiqa to'xtab, chuqur nafas oling — kun tugadi."),
    ("n_ijobiy_4", "Bugungi qiyinchilik ertangi tajribangizga aylanadi — bu ham o'tadi."),
    ("n_uyqu_3", "Yotishdan oldin xona havosini yangilash uyqu sifatini yaxshilaydi."),
    ("n_tartib_4", "Stol ustini tozalab qoldirish — ertaga ishga tez kirishishga yordam beradi."),
    ("n_minnat_4", "Bugun kimdir sizga yordam berdimi? Buni unutmang va imkon bo'lsa, javob qaytaring."),
    ("n_dam_4", "Ekrandan bir muddat uzoqlashish — ko'z va ongga dam berishning oddiy yo'li."),
    ("n_tayyor_4", "Ertangi transport yoki yo'l vaqtini bugun rejalashtirib qo'yish sarosimani kamaytiradi."),
    ("n_ijobiy_5", "Xayrli tun — ertaga yana yangi imkoniyatlar kutmoqda."),
    ("n_oila_4", "Kun davomida band bo'lgan bo'lsangiz ham, yaqinlaringizga bir necha iliq so'z ayting."),
    ("n_tartib_5", "Kerakli hujjat yoki buyumni joyiga qo'yib chiqish — ertangi izlanishni oldini oladi."),
    ("n_minnat_5", "Bugun o'z ustingizda qilgan kichik mehnatingiz uchun ham o'zingizni tabriklang."),
    ("n_dam_5", "Uzoq kun charchoq keltirsa ham, ertaga yangi kuch bilan kelishga ishoning."),
]


def is_valid_advice(text: str | None) -> bool:
    """Uzun yoki bo'sh matnni rad etadi — bunday holatda chaqiruvchi
    original (tayyor bank) matnini ishlatishi kerak. Matn AVTOMATIK
    QISQARTIRILMAYDI (noqulay yarim jumla chiqmasligi uchun) — yoki
    to'liq mos, yoki butunlay rad etiladi.
    """
    if not text or not text.strip():
        return False
    return len(text.strip()) <= _MAX_ADVICE_LENGTH


def _pick_from_bank(bank: list[tuple[str, str]], post_type: str, lookback: int = 30) -> tuple[str, str]:
    # Lookback bank hajmidan kichik bo'lmasligi kerak — aks holda tanlov
    # doim bank BOSHIDAGI yozuvlarga tarafkashlik qilib, oxirgi
    # yozuvlarga hech qachon yetib bormas edi (masalan 35 ta yozuvli
    # bank + 30 kunlik oyna: 31-yozuv hech qachon tanlanmay qolardi).
    # Kattaroq oyna "oxirgi 30 kunda takrorlanmasin" talabini yumshatmaydi
    # (aksincha yanada qat'iyroq) — faqat butun bank aylanib chiqishini
    # kafolatlaydi.
    effective_lookback = max(lookback, len(bank))
    recent_keys = set(saturn_repo.get_recent_content_keys(post_type, limit=effective_lookback))
    for key, text in bank:
        if key not in recent_keys:
            return key, text
    # Bank tugagan (hammasi oxirgi ``lookback`` postda ishlatilgan) —
    # xuddi mavjud ``_pick_tip()`` naqshi bo'yicha, birinchisiga qaytiladi
    # (xabar yuborish hech qachon to'xtamasligi kerak).
    return bank[0]


async def _ai_rephrase(client: AsyncOpenAI, original_text: str, tone_hint: str) -> str:
    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                f"Sen Saturn kompaniyasi uchun {tone_hint} qisqa maslahat matnini BOSHQACHA "
                "so'zlar bilan qayta yoz. MA'NOSINI o'zgartirma, yangi mavzu qo'shma, uzunligini "
                "oshirma (120 belgidan oshmasin, bitta qisqa jumla). O'zbek tilida yoz. Tibbiy, "
                "huquqiy, siyosiy yoki bahsli mazmun QO'SHMA. Faqat qayta yozilgan matnni qaytar, "
                "boshqa hech narsa yozma."
            ),
            input=original_text,
        )
        return (response.output_text or "").strip()
    except Exception as error:
        logger.warning("OpenAI xatosi (saturn_content rephrase): %r", error)
        return ""


async def pick_morning_advice(client: AsyncOpenAI | None) -> tuple[str, str]:
    """``(bank_key, matn)`` qaytaradi — avval bankdan (oxirgi 30 kunda
    ishlatilmagan mavzu) tanlanadi, so'ng (AI mavjud bo'lsa) xilma-xillik
    uchun qayta ifodalanadi. AI natijasi yaroqsiz bo'lsa yoki AI
    ishlamasa, original bank matni ishlatiladi. ``bank_key`` HAR DOIM
    original mavzu kaliti — takrorlanishni oldini olish shu kalit
    bo'yicha ishlaydi, matn AI tomonidan qayta ifodalangan bo'lsa ham.
    """
    key, original = _pick_from_bank(MORNING_ADVICE_BANK, "morning_advice")
    if client is None:
        return key, original

    rephrased = await _ai_rephrase(client, original, "ertalabki, ishga oid")
    return key, (rephrased if is_valid_advice(rephrased) else original)


async def pick_night_advice(client: AsyncOpenAI | None) -> tuple[str, str]:
    """``pick_morning_advice`` bilan bir xil mantiq, tungi bank uchun."""
    key, original = _pick_from_bank(NIGHT_ADVICE_BANK, "night_advice")
    if client is None:
        return key, original

    rephrased = await _ai_rephrase(client, original, "kechqurungi, dam olish/tayyorgarlikka oid")
    return key, (rephrased if is_valid_advice(rephrased) else original)
