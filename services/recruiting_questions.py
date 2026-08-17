"""Fokus HR — lavozimga mos vaziyatli savollar banki.

Har bir savol ``(key, text)`` — kalit tahlil/rubrika/audit uchun
barqaror identifikator. Matematik savol alohida (``MATH_QUESTIONS``) —
javob variantlari bilan, chunki u erkin matn emas, aniq tekshiriladigan
tanlov (inline tugmalar orqali, xato erkin-matn tahlilidan qochish
uchun).

Savollar oddiy, xalqchil tilda yozilgan — "protsedura", "protokol",
"eskalatsiya" kabi rasmiy/tushunarsiz so'zlar ATAYLAB ishlatilmaydi
(qarang loyihaning rekruting talab hujjati, "REAL TESTDA TOPILGAN
MUAMMOLAR" #3).

Faqat ish bilan bog'liq mezonlar so'raladi — himoyalangan shaxsiy
xususiyat (din, millat, oilaviy holat va h.k.) haqida HECH QACHON
savol yo'q.
"""

QUESTION_BANK_VERSION = 2

# Ikkala lavozim uchun umumiy — real testda "ishga kech qolish" holati
# hech qachon so'ralmagani aniqlangan edi.
COMMON_QUESTIONS: list[tuple[str, str]] = [
    ("umumiy_kech_qolish", "Ishga kech qolishingiz yoki kelolmasligingiz aniq bo'lsa, nima qilasiz?"),
]

KASSIR_QUESTIONS: list[tuple[str, str]] = [
    ("kassir_kamomad", "Smena oxirida kassada pul kam chiqsa, nima qilasiz va kimga aytasiz?"),
    ("kassir_narx_farqi", "Peshtaxtadagi narx bilan kassadagi narx boshqacha chiqsa, nima qilasiz?"),
    ("kassir_telefon", "Navbat ko'paygan paytda telefoningiz jiringlasa, nima qilasiz?"),
    ("kassir_login", "Hamkasbingiz login yoki kassangizni so'rasa, berasizmi?"),
    ("kassir_javobgarlik", "Sizning kassangizga boshqa odam kirib, keyin kamomad chiqsa, kim javobgar bo'lishi kerak deb o'ylaysiz?"),
    ("kassir_janjal", "Jahli chiqqan xaridor bilan qanday gaplashasiz?"),
    ("kassir_muddat", "Muddati o'tgan mahsulotni ko'rib qolsangiz, nima qilasiz?"),
] + COMMON_QUESTIONS

SOTUVCHI_QUESTIONS: list[tuple[str, str]] = [
    ("sotuvchi_kutib_olish", "Do'konga kirgan xaridorni qanday kutib olasiz?"),
    ("sotuvchi_ehtiyoj", "Xaridorning nima izlayotganini qanday bilib olasiz?"),
    ("sotuvchi_topilmasa", "So'ralgan mahsulot bo'lmasa, nima taklif qilasiz?"),
    ("sotuvchi_norozilik", "Xaridor noroziligini qanday hal qilasiz?"),
    ("sotuvchi_qoshimcha", "Qo'shimcha mahsulotni bosim qilmasdan qanday tavsiya qilasiz?"),
    ("sotuvchi_javon", "Javon bo'sh yoki tartibsiz ekanini ko'rsangiz, nima qilasiz?"),
    ("sotuvchi_muddat", "Muddati o'tgan mahsulotni ko'rib qolsangiz, nima qilasiz?"),
    ("sotuvchi_kelishmovchilik", "Hamkasbingiz bilan kelishmovchilik chiqsa, qanday hal qilasiz?"),
] + COMMON_QUESTIONS

ROLE_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "kassir": KASSIR_QUESTIONS,
    "sotuvchi": SOTUVCHI_QUESTIONS,
}

# Savol kalitlaridan qaysi biri "muddati o'tgan mahsulot" va "kamomad"
# vaziyatiga tegishli ekanini bildiradi — ``services/recruiting_redflags.py``
# shu kalitlar bo'yicha maxsus (kritik) tahlil qiladi.
EXPIRED_PRODUCT_QUESTION_KEYS = {"kassir_muddat", "sotuvchi_muddat"}
SHORTAGE_QUESTION_KEYS = {"kassir_kamomad", "kassir_javobgarlik"}
CREDENTIAL_SHARING_QUESTION_KEYS = {"kassir_login"}
CUSTOMER_CONFLICT_QUESTION_KEYS = {"kassir_janjal", "sotuvchi_norozilik"}


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
