"""Fokus HR — kritik xavf (red flag) aniqlash: muddati o'tgan mahsulot,
kamomaddan javobgarlikni bo'yniga olmaslik, login/kassa ulashish,
xaridor bilan mojaro kuchaytirish.

REAL TELEGRAM SINOVIDA topilgan asosiy kamchilik: eski baholash faqat
javob UZUNLIGIGA qarab ball berardi (``_score_by_length``), shu sabab
"muddati o'tgan mahsulotni sotsam bo'ladi, hech kim bilmaydi" kabi
xavfli, lekin uzun/aniq javob YAXSHI baholanardi. Bu modul MAZMUNGA
qarab uch holatni ajratadi:

- ``RED``   — aniq xavfli signal (masalan sotish niyati, yashirish).
- ``GREEN`` — aniq to'g'ri harakat (masalan rahbarga xabar berish).
- ``UNCLEAR`` — ikkalasi ham aniq emas: bu holatda BALL BERILMAYDI va
  chaqiruvchi kod (``recruiting_bot.py``) aniqlashtiruvchi savol so'raydi
  — AI/deterministik tizim hech qachon nomzod o'rniga ma'no o'ylab
  topmaydi (qarang loyihaning rekruting talab hujjati).

Faqat kalit so'z asosidagi (deterministik) tahlil — AI mavjud bo'lmasa
ham har doim ishlaydi, xatosiz va tarmoqqa chiqmasdan."""

RED = "red"
GREEN = "green"
UNCLEAR = "unclear"

EXPIRED_PRODUCT = "expired_product"
SHORTAGE_COVERUP = "shortage_coverup"
CREDENTIAL_SHARING = "credential_sharing"
CUSTOMER_CONFLICT = "customer_conflict"
THEFT_COVERUP = "theft_coverup"
PROPERTY_HONESTY = "property_honesty"

_RED_FLAG_LABELS: dict[str, str] = {
    EXPIRED_PRODUCT: "Muddati o'tgan mahsulotni sotishga tayyor",
    SHORTAGE_COVERUP: "Kamomadni yashiradi yoki javobgarlikdan qochadi",
    CREDENTIAL_SHARING: "Login/kassa ma'lumotini boshqaga beradi",
    CUSTOMER_CONFLICT: "Xaridor bilan mojaroni kuchaytiradi",
    THEFT_COVERUP: "O'g'irlikni yashiradi yoki unga qo'shiladi",
    PROPERTY_HONESTY: "Oldingi ish joyida mahsulotni ruxsatsiz olgan/yegan",
}


def label_for(red_flag_key: str) -> str:
    return _RED_FLAG_LABELS.get(red_flag_key, red_flag_key)


def _normalize(text: str) -> str:
    return (text or "").strip().lower().replace("‘", "'").replace("’", "'")


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


# ------------------------------------------------------- muddati o'tgan --

_EXPIRED_SELL_INTENT = (
    "sotaman", "sotib yuboraman", "sota beraman", "sotsam bo'ladi",
    "sotish mumkin", "sotsa bo'ladi", "hech kim bilmaydi", "hech kim bilmasa",
    "muammo emas", "ahamiyati yo'q", "baribir sotiladi", "kim bilibdi",
    "sezmaydi", "shunchaki sotib yuboraman", "arzonlashtirib sotaman",
    "chegirma qilib sotaman",
)
_EXPIRED_CORRECT_ACTION = (
    "olib tashlayman", "javondan olib", "javondan chiqarib", "chetga olib",
    "ajratib qo'yaman", "ajratib qoyaman", "rahbarga aytaman", "rahbarga xabar",
    "qaytarib beraman", "hisobdan chiqaraman", "sotmayman", "sotib bo'lmaydi",
    "sotilmaydi", "utilizatsiya", "menejerga aytaman", "yo'q qilaman",
    "chiqarib tashlayman",
)


def check_expired_product(answer_text: str) -> str:
    text = _normalize(answer_text)
    if not text:
        return UNCLEAR
    sell = _contains_any(text, _EXPIRED_SELL_INTENT)
    correct = _contains_any(text, _EXPIRED_CORRECT_ACTION)
    if sell and not correct:
        return RED
    if correct and not sell:
        return GREEN
    if sell and correct:
        # Ikkalasi ham bor — masalan "olib tashlayman, lekin arzon
        # bo'lsa sotib yuboraman" — bu ham xavfli, sotish niyati ustun.
        return RED
    return UNCLEAR


# ------------------------------------------------------------- kamomad --

_SHORTAGE_AVOIDANCE = (
    "hech kimga aytmayman", "aytmayman", "yashiraman", "sir saqlayman",
    "o'zim to'ldirib qo'yaman", "o'zim qoplayman", "jim turaman",
    "e'tibor bermayman", "ahamiyat bermayman", "boshqasining aybi",
    "mening aybim emas", "menga aloqasi yo'q", "bilmayman kim qilgan",
    "hech narsa qilmayman",
)
_SHORTAGE_REPORTING = (
    "rahbarga aytaman", "rahbarga xabar", "hisobotga yozaman",
    "hisobga olaman", "tekshiraman", "menejerga aytaman", "darhol aytaman",
    "qayta sanayman", "kamerani ko'raman", "yozib qo'yaman", "xabar beraman",
    # O'z javobgarligini tan olish ham ijobiy signal — "kim javobgar"
    # tarzida so'ralgan savolga (masalan ``kassir_javobgarlik``) javob
    # berganda "rahbarga aytaman" emas, aynan shu ko'rinishda javob
    # berish tabiiy (real Telegram sinovida topilgan noto'g'ri UNCLEAR
    # klassifikatsiyasi tuzatildi).
    "javobgarman", "javobgar bo'lishi kerak", "javobgarlikni o'z zimmamga",
    "mas'ulman", "o'zim javobgarman", "kassa egasi javobgar",
)


def check_shortage_response(answer_text: str) -> str:
    text = _normalize(answer_text)
    if not text:
        return UNCLEAR
    avoids = _contains_any(text, _SHORTAGE_AVOIDANCE)
    reports = _contains_any(text, _SHORTAGE_REPORTING)
    if avoids and not reports:
        return RED
    if reports:
        return GREEN
    return UNCLEAR


# --------------------------------------------------- login/kassa ulashish --

_CREDENTIAL_SHARE_INTENT = (
    "kassamni beraman", "kassani beraman", "loginimni beraman", "login beraman",
    "parolimni beraman", "parolni beraman", "hisobimni beraman",
    "kirish ma'lumotlarimni beraman", "beraman albatta", "ha, beraman",
)
_CREDENTIAL_REFUSE = (
    "bermayman", "hech kimga bermayman", "hech qachon bermayman",
    "faqat o'zim ishlataman", "yo'q, bera olmayman",
)


def check_credential_sharing(answer_text: str) -> str:
    text = _normalize(answer_text)
    if not text:
        return UNCLEAR
    shares = _contains_any(text, _CREDENTIAL_SHARE_INTENT)
    refuses = _contains_any(text, _CREDENTIAL_REFUSE)
    if shares and not refuses:
        return RED
    if refuses:
        return GREEN
    return UNCLEAR


# --------------------------------------------------------- xaridor mojaro --

_CONFLICT_ESCALATION = (
    "men ham baqiraman", "javob qaytaraman", "haqorat qilaman", "janjallashaman",
    "chiqib ket deyman", "kerak emassiz desam bo'ladi", "gap qaytaraman",
    "unga ham qattiq gapiraman", "jerkillayman",
)
_CONFLICT_DEESCALATION = (
    "xotirjam", "tinchlantiraman", "tinglayman", "kechirim so'rayman",
    "yechim topaman", "rahbarga chaqiraman", "muloyimlik bilan",
    "sabr bilan", "tushunishga harakat",
)


def check_customer_conflict(answer_text: str) -> str:
    text = _normalize(answer_text)
    if not text:
        return UNCLEAR
    escalates = _contains_any(text, _CONFLICT_ESCALATION)
    deescalates = _contains_any(text, _CONFLICT_DEESCALATION)
    if escalates and not deescalates:
        return RED
    if deescalates:
        return GREEN
    return UNCLEAR


# ---------------------------------------------------------------- o'g'irlik --

_THEFT_COVERUP = (
    "hech kimga aytmayman", "sezmaganman deyman", "indamayman", "jim turaman",
    "yashiraman", "men ham olib qolaman", "menga nima", "aralashmayman",
    "ko'rmaganga olaman", "bilmasman deyman", "aybini ochib qo'ymayman",
)
_THEFT_REPORTING = (
    "rahbarga aytaman", "rahbarga xabar", "menejerga aytaman", "darhol xabar beraman",
    "ogohlantiraman", "to'xtataman", "yo'l qo'ymayman", "kamerani ko'raman",
    "xabar beraman", "aytmasdan qolmayman", "jim turmayman",
)


def check_theft_witness(answer_text: str) -> str:
    """Hamkasb o'g'irlik qilganini ko'rib qolish vaziyati — yashirish
    yoki unga qo'shilish KRITIK xavf (qarang loyihaning rekruting talab
    hujjati: "O'g'irlikni yashirish yoki unga qo'shilish — kritik red
    flag bo'lsin")."""
    text = _normalize(answer_text)
    if not text:
        return UNCLEAR
    covers = _contains_any(text, _THEFT_COVERUP)
    reports = _contains_any(text, _THEFT_REPORTING)
    if covers and not reports:
        return RED
    if reports:
        return GREEN
    return UNCLEAR


# ------------------------------------------------ mulkka munosabat (o'zi) --

_PROPERTY_TAKING_ADMISSION = (
    "qirqib yesam", "qirqib yegan", "kesib yesam", "kesib yegan", "ochib yesam",
    "yeb qo'yardim", "yeb yurardim", "yeb qo'ygan", "olib ketardim", "olib qo'yardim",
    "ruxsatsiz oldim", "ruxsatsiz yedim", "sotib olmasdan yedim", "sotib olmasdan olardim",
    "pulini to'lamasdan", "hisobga olmasdan oldim", "shunchaki olardim", "shunchaki yerdim",
)


def check_property_honesty(answer_text: str) -> str:
    """Nomzodning O'ZI haqida — oldingi ish joyida do'kon mahsulotini
    ruxsatsiz olgan/yeganini bilvosita aytib qo'yishi (masalan "nega
    ketdingiz" degan ochiq savolga javob berayotganda). Bu ``check_theft_witness``dan
    farqli — u yerda hamkasbning o'g'irligiga guvoh bo'lish so'raladi,
    bu yerda esa nomzodning o'z xatti-harakati haqida ochiq savolga
    berilgan erkin javobda tasodifan chiqib qolgan admission aniqlanadi.
    Faqat RED yoki (signal yo'q bo'lsa) "neytral" natija bor — bu ochiq
    savol bo'lgani uchun "to'g'ri javob"ning o'zi yo'q, shuning uchun
    ``GREEN`` shunchaki "signal topilmadi" degani, ijobiy baho emas."""
    text = _normalize(answer_text)
    if not text:
        return UNCLEAR
    if _contains_any(text, _PROPERTY_TAKING_ADMISSION):
        return RED
    return GREEN
