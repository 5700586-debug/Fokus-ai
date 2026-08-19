"""Fokus HR — vaziyatli savollar banki.

Har bir savol ``(key, text)`` — kalit tahlil/rubrika/audit uchun
barqaror identifikator. Matematik savol alohida (``MATH_QUESTIONS``) —
javob variantlari bilan, chunki u erkin matn emas, aniq tekshiriladigan
tanlov (inline tugmalar orqali, xato erkin-matn tahlilidan qochish
uchun).

QUESTION_BANK_VERSION 4: suhbat qisqartirildi — endi FAQAT 4 ta
umumiy (ikkala lavozim uchun bir xil) vaziyatli savol + 1 ta qisqa
operatsion tekshiruv (muddati o'tgan mahsulot). Qolgan 2 ta "asosiy 6
psixologik savol"dan ikkitasi (motivatsiya/ketish sababi va ish
barqarorligi) E bo'limida EMAS — ular D bo'limida allaqachon mavjud
(``recruiting_bot.py``dagi ``leave_reason``/``job_stability`` qadamlari).
Lavozimga xos ko'p sonli qo'shimcha savollar (narx farqi, telefon,
login, kamomad, kutib olish, javon va h.k.) real Telegram sinovidan
keyin ATAYLAB OLIB TASHLANDI — suhbat charchatmasin, lekin muhim
signallar (mijoz bilan muomala, halollik, savdo fikrlashi,
tashabbuskorlik) saqlansin.

Savollar oddiy, xalqchil tilda yozilgan — "protsedura", "protokol",
"eskalatsiya" kabi rasmiy/tushunarsiz so'zlar ATAYLAB ishlatilmaydi.

Faqat ish bilan bog'liq mezonlar so'raladi — himoyalangan shaxsiy
xususiyat (din, millat, oilaviy holat va h.k.) haqida HECH QACHON
savol yo'q.
"""

QUESTION_BANK_VERSION = 4

# 6 ta asosiy psixologik erkin-javobli savoldan 4 tasi — ikkala
# lavozim uchun bir xil (qarang loyihaning rekruting talab hujjati:
# "ASOSIY 6 TA ERKIN JAVOBLI SAVOL"). Qolgan 2 tasi (motivatsiya/ketish
# sababi, ish barqarorligi) D bo'limida so'raladi.
CORE_QUESTIONS: list[tuple[str, str]] = [
    ("core_mijoz_qopol", "Jahli chiqqan xaridor sizga qo'pol gapirsa, nima qilasiz?"),
    ("core_mahsulot_yoq", "Xaridor so'ragan mahsulot bo'lmasa, nima qilasiz?"),
    (
        "core_halollik",
        "Rahbar yo'q paytda hamkasbingiz do'kondagi mahsulotni yashirib olsa yoki yeb qo'ysa, nima qilasiz?",
    ),
    ("core_tashabbus", "Ish tinch, xaridor kam va sizga hozircha vazifa berilmagan. Nima qilasiz?"),
]

# Muddati o'tgan mahsulot — asosiy 6 psixologik savol qatoridan
# ATAYLAB chiqarilgan, lekin qisqa OPERATSION tekshiruv sifatida
# saqlanadi (aniq javob bo'lsa follow-up berilmaydi — qarang
# services/recruiting_followup.py).
OPERATIONAL_QUESTIONS: list[tuple[str, str]] = [
    ("core_muddat", "Muddati o'tgan mahsulotni ko'rsangiz nima qilasiz?"),
]

ROLE_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "kassir": CORE_QUESTIONS + OPERATIONAL_QUESTIONS,
    "sotuvchi": CORE_QUESTIONS + OPERATIONAL_QUESTIONS,
}

# Savol kalitlaridan qaysi biri qaysi kritik (red-flag) kategoriyaga
# tegishli ekanini bildiradi — ``services/recruiting_redflags.py`` shu
# kalitlar bo'yicha maxsus tahlil qiladi. Kassa xavfsizligi (login
# ulashish) va kamomad/javobgarlik savollari endi so'ralmagani uchun
# bo'sh to'plam — tekshiruvchi funksiyalarning o'zi
# (``check_credential_sharing``, ``check_shortage_response``) hali ham
# mavjud, faqat hech qanday faol savolga bog'lanmagan.
EXPIRED_PRODUCT_QUESTION_KEYS = {"core_muddat"}
SHORTAGE_QUESTION_KEYS: set[str] = set()
CREDENTIAL_SHARING_QUESTION_KEYS: set[str] = set()
CUSTOMER_CONFLICT_QUESTION_KEYS = {"core_mijoz_qopol"}
THEFT_QUESTION_KEYS = {"core_halollik"}


class MathChoice:
    __slots__ = ("key", "label")

    def __init__(self, key: str, label: str):
        self.key = key
        self.label = label


class MathQuestion:
    __slots__ = ("key", "text", "choices", "correct_key")

    def __init__(self, key: str, text: str, choices: list[MathChoice], correct_key: str):
        self.key = key
        self.text = text
        self.choices = choices
        self.correct_key = correct_key


# Faqat kassir uchun — oddiy qaytim hisoblash, aniq tekshiriladigan
# tanlov ko'rinishida (erkin matndan raqam ajratish xato/aniqmaslikka
# olib kelishi mumkin edi). Tugma orqali — deterministik.
MATH_QUESTIONS: dict[str, MathQuestion] = {
    "kassir": MathQuestion(
        key="kassir_qaytim",
        text=(
            "Mahsulot narxi 12 350 so'm. Xaridor 20 000 so'm bilan to'ladi. "
            "Qancha qaytim berasiz?"
        ),
        choices=[
            MathChoice("a", "6 650 so'm"),
            MathChoice("b", "7 650 so'm"),
            MathChoice("c", "8 650 so'm"),
            MathChoice("d", "7 350 so'm"),
        ],
        correct_key="b",
    ),
}


def questions_for(position_key: str) -> list[tuple[str, str]]:
    return ROLE_QUESTIONS.get(position_key, [])


def math_question_for(position_key: str) -> MathQuestion | None:
    return MATH_QUESTIONS.get(position_key)
