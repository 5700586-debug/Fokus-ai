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
from services import saturn_image

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"
# Har bir maslahat — salomlashuvdan tashqari FAQAT bitta qisqa gap: bitta
# amaliy harakat yoki foydali fikr. Maqsad 60-90 belgi, 100 belgidan HECH
# QACHON oshmaydi (rasmda ko'pi bilan 2 qator bo'lishi kerak — qarang
# services/saturn_image.py: _MAX_ADVICE_LINES).
_MAX_ADVICE_LENGTH = 100

# ------------------------------------------------------------- tonggi bank --
# Mavzular: savdo/xizmat, muomala, tozalik/tartib, mahsulot joylash,
# jamoaviylik, diqqat, rivojlanish, ishni yengillashtirish, sog'liq.
MORNING_ADVICE_BANK: list[tuple[str, str]] = [
    ("m_sav_1", "Xaridor kirganda tabassum bilan salomlashing."),
    ("m_sav_2", "Xaridorni tinglang, gapini bo'lmang."),
    ("m_sav_3", "Mos qo'shimcha mahsulotni ham taklif qiling."),
    ("m_sav_4", "Savol beruvchi xaridorni shoshiltirmang."),
    ("m_sav_5", "Navbat uzayganda ham xotirjam bo'ling."),
    ("m_sav_6", "Bilmagan savolga taxmin bilan javob bermang."),
    ("m_muo_1", "Norozi xaridorni avval to'liq tinglang."),
    ("m_muo_2", "Xaridorga ismi bilan murojaat qiling."),
    ("m_muo_3", "Janjal chiqsa, ovozingizni ko'tarmang."),
    ("m_muo_4", "Kimningdir kayfiyatini shaxsiy qabul qilmang."),
    ("m_muo_5", "Xaridorga yolg'on va'da bermang."),
    ("m_muo_6", "Kutish uzunroq bo'lsa, buni aytib qo'ying."),
    ("m_toz_1", "Vitrina va javonni toza tuting."),
    ("m_toz_2", "Smena boshida ish joyingizni tekshiring."),
    ("m_toz_3", "Muddati o'tgan mahsulotni har kuni tekshiring."),
    ("m_toz_4", "Ish kiyimingizga ozoda qarang."),
    ("m_joy_1", "Ko'p sotiladigan mahsulotni ko'z balandligiga qo'ying."),
    ("m_jam_1", "Hamkasbingizga yordam qo'lini cho'zing."),
    ("m_jam_2", "Bugun kimgadir rahmat ayting."),
    ("m_jam_3", "Yangi hamkasbdan savol berishdan tortinmang."),
    ("m_jam_4", "Rahbaringiz fikrini ochiq tinglang."),
    ("m_diq_1", "Kun boshida asosiy 3 vazifani belgilang."),
    ("m_diq_2", "Telefon bilan ovora bo'lib xaridorni unutmang."),
    ("m_diq_3", "Ishni \"keyinroq\" demasdan darhol bajaring."),
    ("m_riv_1", "Har kuni bitta yangi narsa o'rganing."),
    ("m_riv_2", "Xato qilsangiz, uni yashirmasdan tan oling."),
    ("m_riv_3", "Kichik muvaffaqiyatingizni ham qadrlang."),
    ("m_yen_1", "Kerakli buyumlarni oldindan tayyorlab qo'ying."),
    ("m_yen_2", "Takrorlanadigan ishni soddalashtiring."),
    ("m_vaq_1", "Kun boshida rejangizni tuzib oling."),
    ("m_sal_1", "Kuniga yetarlicha suv iching."),
    ("m_sal_2", "Ish orasida o'z vaqtida ovqatlaning."),
    ("m_sal_3", "Har 1-2 soatda bir oz cho'zilib oling."),
    ("m_sal_4", "Bugun ertaroq yotishga harakat qiling."),
    ("m_gig_1", "Pul bilan ishlaganda qo'l gigiyenasiga e'tibor bering."),
    ("m_sav_7", "Ikkilanayotgan xaridorga bosim qilmang."),
    ("m_sav_8", "Yangi mahsulotni qisqa va aniq tanishtiring."),
    ("m_sav_9", "Xato mahsulot qaytarsa, xotirjam yordam bering."),
    ("m_toz_5", "Yerga tushgan chiqindini darhol yig'ishtiring."),
    ("m_toz_6", "Kassa atrofini ham tartibda tuting."),
    ("m_toz_7", "Hidli mahsulotni darhol chetga oling."),
    ("m_jam_5", "Charchagan hamkasbingizdan hol so'rang."),
    ("m_jam_6", "O'z vazifangizni to'liq bajaring."),
    ("m_jam_7", "Kelishmovchilikni hurmat bilan hal qiling."),
    ("m_riv_4", "Hamkasbingizdan yangi usul so'rab o'rganing."),
    ("m_riv_5", "Bugun bir vazifani o'z ixtiyoringiz bilan bajaring."),
    ("m_riv_6", "Ishni tugatgach, yordam kerakmi deb so'rang."),
    ("m_vaq_2", "Smenaga bir necha daqiqa oldin yetib keling."),
    ("m_vaq_3", "Kechikishingizni oldindan xabar qiling."),
    ("m_vaq_4", "Tanaffusdan o'z vaqtida qayting."),
    ("m_joy_2", "Eski sanali mahsulotni oldinga joylashtiring."),
    ("m_joy_3", "Bo'sh javonni bugun tartibga soling."),
    ("m_joy_4", "Narx yorlig'i mahsulotga mosligini tekshiring."),
    ("m_kas_1", "Kassani boshqa birovga topshirmang."),
    ("m_kas_2", "Chekni berishdan oldin summani tekshiring."),
    ("m_kas_3", "Smena oxirida kassani ikki marta tekshiring."),
    ("m_kas_4", "Naqd pul bilan ishlaganda diqqatingizni jamlang."),
    ("m_kas_5", "Kassadagi nomuvofiqlikni darhol rahbarga ayting."),
    ("m_log_1", "Shaxsiy login yoki parolingizni hech kimga bermang."),
    ("m_log_2", "Boshqa birovning hisobi bilan tizimga kirmang."),
    ("m_log_3", "Ketayotganda tizimdan chiqishni unutmang."),
    ("m_narx_1", "Narxni bilmasangiz, taxmin qilmasdan tekshiring."),
    ("m_narx_2", "Aksiya shartlarini avval o'zingiz aniqlang."),
    ("m_narx_3", "Mahsulot muddatini qadoqdan birga tekshiring."),
    ("m_tel_1", "Ish vaqtida shaxsiy suhbatni keyinga qoldiring."),
    ("m_tel_2", "Zarur qo'ng'iroqni tez va qisqa tugating."),
    ("m_tel_3", "Ijtimoiy tarmoqni faqat tanaffusda ko'ring."),
    ("m_qsh_1", "Qo'shimcha mahsulotni faqat mos kelganda taklif qiling."),
    ("m_qsh_2", "Xaridor \"yo'q\" desa, darhol to'xtating."),
    ("m_qsh_3", "Taklif qilayotgan mahsulotni o'zingiz yaxshi biling."),
    ("m_ozt_1", "Band vaqtda ham ovozingizni past saqlang."),
    ("m_ozt_2", "G'azablansangiz, chuqur nafas oling."),
    ("m_ozt_3", "Charchagan bo'lsangiz ham qattiq gapirmang."),
    ("m_ozt_4", "Stressdan keyin bir necha daqiqa tinchlaning."),
    ("m_yech_1", "Muammoga \"iloji yo'q\" demang, yechim taklif qiling."),
    ("m_yech_2", "Xato bo'lsa, avval uni tuzatishni o'ylang."),
    ("m_yech_3", "Yechim topolmasangiz, hamkasbdan maslahat so'rang."),
    ("m_yech_4", "Har muammoni o'rganish imkoniyati deb bilib qarang."),
    ("m_mas_1", "O'z zimmangizga olgan ishni oxirigacha yetkazing."),
    ("m_mas_2", "Xato qilsangiz, uni tan oling."),
    ("m_mas_3", "Vazifani unutmaslik uchun yozib qo'ying."),
    ("m_mas_4", "Bergan va'dangizni bajaring."),
    ("m_smn_1", "Smenani tugatishdan oldin ish joyini tayyorlang."),
    ("m_smn_2", "Qoldirilgan ishni keyingi smenaga aniq ayting."),
    ("m_smn_3", "Asboblarni o'z joyiga qaytarib qo'ying."),
    ("m_smn_4", "Smena topshirishda shoshilmang."),
    ("m_xvf_1", "Og'ir yukni tizzangizga tayanib ko'taring."),
    ("m_xvf_2", "Nam yoki sirg'anchiq polni darhol belgilang."),
    ("m_xvf_3", "Elektr asboblarda ko'rsatmaga qat'iy amal qiling."),
    ("m_xvf_4", "Xavfli holatni ko'rsangiz, darhol xabar bering."),
]

# -------------------------------------------------------------- tungi bank --
# Mavzular: dam olish, minnatdorchilik, ertangi kunga tayyorgarlik,
# ish joyini tartibga solish, ijobiy fikrlash, uyqu.
NIGHT_ADVICE_BANK: list[tuple[str, str]] = [
    ("n_tartib_1", "Ish joyini tartibli qoldiring."),
    ("n_minnat_1", "Bugungi mehnatingiz uchun o'zingizga rahmat ayting."),
    ("n_tayyor_1", "Ertangi ustuvor vazifangizni belgilab qo'ying."),
    ("n_uyqu_1", "Uxlashdan oldin telefonni chetga qo'ying."),
    ("n_oila_1", "Oilangiz bilan bugungi kunni ulashing."),
    ("n_ijobiy_1", "Bugun nima yaxshi ketganini o'ylab ko'ring."),
    ("n_tartib_2", "Ertangi buyumlarni bugun tayyorlab qo'ying."),
    ("n_dam_1", "Ish va dam olish orasida chegara qo'ying."),
    ("n_minnat_2", "Sizga yordam bergan hamkasbga rahmat yozing."),
    ("n_ijobiy_2", "Ertangi kun yaxshiroq bo'lishiga ishoning."),
    ("n_uyqu_2", "Erta yotishga harakat qiling."),
    ("n_tayyor_2", "Ertangi rejangizni ko'zdan kechiring."),
    ("n_oila_2", "Yaqiningiz bilan bir necha daqiqa gaplashing."),
    ("n_dam_2", "Charchagan bo'lsangiz, tanangizni tinglang."),
    ("n_tartib_3", "Kunlik ro'yxatingizni tekshirib chiqing."),
    ("n_ijobiy_3", "Kichik yutuqlaringizni ham qadrlang."),
    ("n_minnat_3", "Bugun sizga yaxshi so'z aytgan kishini eslang."),
    ("n_dam_3", "Ish haqidagi o'yni uyga olib kelmang."),
    ("n_tayyor_3", "Ertangi kiyim va buyumlarni tayyorlang."),
    ("n_oila_3", "Uyga kirganda telefonni chetga qo'ying."),
    ("n_ijobiy_4", "Qiyin lahzadan nima o'rganganingizni o'ylang."),
    ("n_uyqu_3", "Yorug' ekrandan oldin uzoqlashing."),
    ("n_tartib_4", "Stol ustini tozalab qoldiring."),
    ("n_minnat_4", "O'zingizga ham rahmat ayting."),
    ("n_dam_4", "Ekrandan bir muddat uzoqlashing."),
    ("n_tayyor_4", "Bugun kechqurun bitta aniq maqsad belgilang."),
    ("n_ijobiy_5", "Har kun mukammal bo'lishi shart emas."),
    ("n_oila_4", "Sevganlaringiz bilan daqiqa o'tkazing."),
    ("n_tartib_5", "Kerakli hujjatni joyiga qo'ying."),
    ("n_minnat_5", "Sizga tabassum ulashgan xaridorni eslang."),
    ("n_dam_5", "Uyqudan oldin tashvishni qog'ozga yozing."),
    ("n_tartib_6", "Ertangi kiyimingizni bugun tayyorlang."),
    ("n_tartib_7", "Ish stolini bo'sh qoldirmang."),
    ("n_tartib_8", "Tugallanmagan ishni ertangi ro'yxatga yozing."),
    ("n_minnat_6", "Bugun sizga yordam bergan kishini unutmang."),
    ("n_minnat_7", "Kichik yordam uchun ham rahmat ayting."),
    ("n_tayyor_5", "Ertangi vazifalarni xayolan ko'rib chiqing."),
    ("n_tayyor_6", "Ertangi yo'l vaqtini bugun rejalashtiring."),
    ("n_tayyor_7", "Ertangi transportni oldindan o'ylab qo'ying."),
    ("n_uyqu_4", "Chuqur nafas olib, tanangizni tinchlantiring."),
    ("n_uyqu_5", "Kechqurun ortiqcha yemasdan uxlang."),
    ("n_uyqu_6", "Yotishdan oldin xona havosini yangilang."),
    ("n_oila_5", "Uyga yetganda chuqur nafas oling."),
    ("n_oila_6", "Bugun band bo'lsangiz ham iliq so'z ayting."),
    ("n_ijobiy_6", "Bugungi qiyinchilik ertangi tajribaga aylanadi."),
    ("n_ijobiy_7", "Kamchilikka emas, ertangi imkoniyatga qarang."),
    ("n_ijobiy_8", "Xayrli tun, ertaga yangi imkoniyat kutmoqda."),
    ("n_dam_6", "Bugun charchoq tabiiy, ertaga kuch qaytadi."),
    ("n_dam_7", "Dam olishga o'zingizga vaqt ajrating."),
    ("n_mij_1", "Sizga rahmat aytgan xaridorni eslang."),
    ("n_mij_2", "Qiyin xaridor bilan sabringiz uchun o'zingizni tabriklang."),
    ("n_mij_3", "Ertaga yangi xaridorlarni samimiy kutib oling."),
    ("n_mij_4", "Bugungi foydali javobingiz qimmatli hissa edi."),
    ("n_mij_5", "Xaridor mamnun bo'lsa, bu bugungi eng katta yutug'ingiz."),
    ("n_mij_6", "Ertaga ham birinchi taassurotga e'tibor bering."),
    ("n_mij_7", "Sabr bilan tushuntirganingiz uchun o'zingizni maqtang."),
    ("n_mij_8", "Bugungi har bir yaxshi muomalangiz qimmatli edi."),
    ("n_toz_1", "Ketishdan oldin ish joyingizni ko'zdan kechiring."),
    ("n_toz_2", "Bugun tartibga keltirgan joyingiz ertaga qulaylik beradi."),
    ("n_toz_3", "Kichik changni ham e'tiborsiz qoldirmang."),
    ("n_toz_4", "Ish joyini toza topshiring."),
    ("n_toz_5", "Tozalikka ajratgan vaqtingiz ertaga foyda beradi."),
    ("n_toz_6", "Ketishdan oldin chiqindi qolmaganini tekshiring."),
    ("n_toz_7", "Toza ish joyi yaxshi taassurot qoldiradi."),
    ("n_toz_8", "Bugun tartibni saqlaganingiz uchun rahmat."),
    ("n_jam_1", "Sizga yordam bergan hamkasbni eslang."),
    ("n_jam_2", "Jamoa bilan o'tkazgan kun uchun rahmat ayting."),
    ("n_jam_3", "Ertaga hamkasbga yordam berishni rejalashtiring."),
    ("n_jam_4", "Bugun kimgadir aytgan yaxshi so'zingiz muhim edi."),
    ("n_jam_5", "Kelishmovchilikni ertangi yangi sahifa deb bilib qarang."),
    ("n_jam_6", "Hamkasbingizning bugungi mehnatini ham qadrlang."),
    ("n_jam_7", "Ertaga jamoaga qanday foydali bo'lishni o'ylang."),
    ("n_jam_8", "Hamkasblaringizga xayrli tun tilang."),
    ("n_xvf_1", "Ketishdan oldin xavfli qolgan narsani tekshiring."),
    ("n_xvf_2", "Elektr asboblarni to'g'ri o'chirib qo'ying."),
    ("n_xvf_3", "Sezgan xavfni hamkasblarga ham aytib qo'ying."),
    ("n_xvf_4", "Eshik-derazalarning yopilganini tekshiring."),
    ("n_xvf_5", "Xavfsizlik qoidalariga rioya qilganingiz uchun tabriklang."),
    ("n_xvf_6", "Ertaga ham xavfsizlikni birinchi o'ringa qo'ying."),
    ("n_xvf_7", "Nam yoki sirg'anchiq joy qolmaganini tekshiring."),
    ("n_xvf_8", "Xavfsiz odat har kunlik kichik e'tibordan iborat."),
    ("n_riv_1", "Bugun o'rgangan narsani xayolda mustahkamlang."),
    ("n_riv_2", "Ertaga o'zingiz uchun kichik qadam belgilang."),
    ("n_riv_3", "Bugungi xatoni ertangi saboq deb bilib uxlang."),
    ("n_riv_4", "Kichik yaxshilanish katta natijaga aylanadi."),
    ("n_riv_5", "Ertaga qiyinroq, foydali bitta vazifa tanlang."),
    ("n_riv_6", "Bugungi kichik izlaringizni ham qadrlang."),
    ("n_riv_7", "Ertangi kun uchun o'zingizga ijobiy so'z ayting."),
    ("n_riv_8", "Rivojlanish shoshilinch emas, sabr qiling."),
    ("n_riv_9", "Ertaga yana bir qadam oldinga qo'yishga tayyor bo'ling."),
]


# --------------------------------------------------- kategoriya guruhlari --
# Har bir bank kaliti (masalan "m_kas_2") allaqachon mavzu prefiksini
# o'zida saqlaydi ("kas") — buni ajratib, kengroq "rotatsiya
# kategoriyasi"ga (masalan "intizom") solishtiramiz. Yangi ustun/jadval
# shart emas — mavjud kalit formatidan foydalaniladi (haftalik mavzu
# muvozanati va "ketma-ket kunda bir xil kategoriya takrorlanmasin"
# qoidasi shu asosda ishlaydi).
_MORNING_CATEGORY_BUCKETS: dict[str, str] = {
    "sav": "xizmat", "muo": "xizmat", "qsh": "xizmat", "narx": "xizmat",
    "toz": "tozalik", "joy": "tozalik",
    "jam": "jamoa",
    "vaq": "intizom", "tel": "intizom", "ozt": "intizom", "xvf": "intizom",
    "kas": "intizom", "log": "intizom", "diq": "intizom",
    "riv": "rivojlanish", "yech": "rivojlanish", "mas": "rivojlanish",
    "smn": "rivojlanish", "yen": "rivojlanish",
    "sal": "salomatlik", "gig": "salomatlik",
}

_NIGHT_CATEGORY_BUCKETS: dict[str, str] = {
    "tartib": "tozalik", "toz": "tozalik",
    "minnat": "jamoa", "jam": "jamoa", "oila": "jamoa",
    "tayyor": "rivojlanish", "riv": "rivojlanish", "ijobiy": "rivojlanish",
    "uyqu": "salomatlik", "dam": "salomatlik",
    "mij": "xizmat",
    "xvf": "intizom",
}


def _key_prefix(key: str) -> str:
    parts = key.split("_")
    return "_".join(parts[1:-1])


def morning_category_of(key: str) -> str:
    return _MORNING_CATEGORY_BUCKETS.get(_key_prefix(key), "boshqa")


def night_category_of(key: str) -> str:
    return _NIGHT_CATEGORY_BUCKETS.get(_key_prefix(key), "boshqa")


def is_valid_advice(text: str | None) -> bool:
    """Uzun, bo'sh yoki rasmda ikki qatorga (eng kichik ruxsat etilgan
    38px shriftda ham) sig'maydigan matnni rad etadi — bunday holatda
    chaqiruvchi original (tayyor bank) matnini ishlatishi kerak. Matn
    AVTOMATIK QISQARTIRILMAYDI va shrift majburan kichraytirilmaydi
    (noqulay yarim jumla yoki o'qib bo'lmas kichik matn chiqmasligi
    uchun) — yoki to'liq mos, yoki butunlay rad etiladi.
    """
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(stripped) > _MAX_ADVICE_LENGTH:
        return False
    return saturn_image.fits_within_advice_lines(stripped)


def _pick_from_bank(
    bank: list[tuple[str, str]],
    post_type: str,
    category_of,
    lookback: int = 90,
) -> tuple[str, str]:
    # Lookback bank hajmidan kichik bo'lmasligi kerak — aks holda tanlov
    # doim bank BOSHIDAGI yozuvlarga tarafkashlik qilib, oxirgi
    # yozuvlarga hech qachon yetib bormas edi (masalan 35 ta yozuvli
    # bank + 30 kunlik oyna: 31-yozuv hech qachon tanlanmay qolardi).
    # Kattaroq oyna "oxirgi N kunda takrorlanmasin" talabini yumshatmaydi
    # (aksincha yanada qat'iyroq) — faqat butun bank aylanib chiqishini
    # kafolatlaydi. Standart 90 kunlik oyna — "bir xil maslahat 90 kun
    # ichida qaytarilmasin" talabiga mos.
    effective_lookback = max(lookback, len(bank))
    recent_keys_list = saturn_repo.get_recent_content_keys(post_type, limit=effective_lookback)
    recent_keys = set(recent_keys_list)
    previous_category = category_of(recent_keys_list[0]) if recent_keys_list else None

    # Rasmda ikki qatorga (38px'da ham) sig'maydigan yozuv bank ichida
    # bo'lishi amalda deyarli mumkin emas (hammasi qisqa yozilgan), lekin
    # himoya sifatida shu yerda ham tekshiriladi — "sig'masa, qisqaroq
    # zaxira maslahat tanlansin" talabi.
    candidates = [
        (key, text)
        for key, text in bank
        if key not in recent_keys and saturn_image.fits_within_advice_lines(text)
    ]
    if not candidates:
        # Bank tugagan (hammasi oxirgi ``lookback`` postda ishlatilgan) —
        # xabar yuborish hech qachon to'xtamasligi kerak, shuning uchun
        # butun bank (sig'adigan yozuvlar) qayta ochiladi.
        candidates = [(key, text) for key, text in bank if saturn_image.fits_within_advice_lines(text)]
    if not candidates:
        # Nazariy jihatdan yetib bo'lmaydigan zaxira — bank yozuvlari doim
        # qisqa yozilgan, lekin xabar yuborish baribir to'xtamasligi kerak.
        candidates = bank[:1]

    # Kecha (oxirgi post)dan boshqa mavzu (kategoriya) tanlashga
    # harakat qilamiz — bir xil mavzu ketma-ket kunlarda takrorlanmasin.
    for key, text in candidates:
        if previous_category is None or category_of(key) != previous_category:
            return key, text

    # Qolgan barcha nomzodlar ham kechagi kategoriyada bo'lsa (masalan
    # bank deyarli tugagan holatda) — baribir yuborish to'xtamaydi.
    return candidates[0]


async def _ai_rephrase(client: AsyncOpenAI, original_text: str, tone_hint: str) -> str:
    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                f"Sen Saturn kompaniyasi uchun {tone_hint} qisqa maslahat matnini BOSHQACHA "
                "so'zlar bilan qayta yoz. MA'NOSINI o'zgartirma, yangi mavzu qo'shma. Natija "
                "FAQAT BITTA qisqa gap bo'lsin — bitta amaliy harakat yoki foydali fikr, ikkinchi "
                "gap yoki qo'shimcha izoh qo'shma. 90 belgidan oshmasin (100 belgidan HECH QACHON "
                "oshmasin). O'zbek tilida yoz. Tibbiy, huquqiy, siyosiy yoki bahsli mazmun QO'SHMA. "
                "Faqat qayta yozilgan matnni qaytar, boshqa hech narsa yozma."
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
    key, original = _pick_from_bank(MORNING_ADVICE_BANK, "morning_advice", morning_category_of)
    if client is None:
        return key, original

    rephrased = await _ai_rephrase(client, original, "ertalabki, ishga oid")
    return key, (rephrased if is_valid_advice(rephrased) else original)


async def pick_night_advice(client: AsyncOpenAI | None) -> tuple[str, str]:
    """``pick_morning_advice`` bilan bir xil mantiq, tungi bank uchun."""
    key, original = _pick_from_bank(NIGHT_ADVICE_BANK, "night_advice", night_category_of)
    if client is None:
        return key, original

    rephrased = await _ai_rephrase(client, original, "kechqurungi, dam olish/tayyorgarlikka oid")
    return key, (rephrased if is_valid_advice(rephrased) else original)
