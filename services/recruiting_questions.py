"""Fokus HR — lavozimga mos vaziyatli savollar banki.

Har bir savol ``(key, text)`` — kalit tahlil/rubrika/audit uchun
barqaror identifikator. Matematik savol alohida (``MATH_QUESTIONS``) —
javob variantlari bilan, chunki u erkin matn emas, aniq tekshiriladigan
tanlov (inline tugmalar orqali, xato erkin-matn tahlilidan qochish
uchun).

Faqat ish bilan bog'liq mezonlar so'raladi — himoyalangan shaxsiy
xususiyat (din, millat, oilaviy holat va h.k.) haqida HECH QACHON
savol yo'q (qarang loyihaning rekruting talab hujjati).
"""

QUESTION_BANK_VERSION = 1

KASSIR_QUESTIONS: list[tuple[str, str]] = [
    ("kassir_kamomad", "Smena oxirida kassa hisobida kamomad chiqsa, nima qilasiz?"),
    ("kassir_narx_farqi", "Peshtaxtadagi narx bilan kassadagi narx farq qilsa, nima qilasiz?"),
    ("kassir_telefon", "Navbat ko'payib turgan paytda telefon qo'ng'iroq qilsa, qanday munosabatda bo'lasiz?"),
    ("kassir_login", "Hamkasbingiz sizning kassangiz yoki login ma'lumotlaringizdan foydalanmoqchi bo'lsa, nima qilasiz?"),
    ("kassir_javobgarlik", "Sizning kassangizga boshqa odam kirgandan keyin kamomad chiqsa, deb o'ylaysiz, javobgarlik kimda bo'lishi kerak?"),
    ("kassir_janjal", "Jahli chiqqan xaridor bilan qanday muomala qilasiz?"),
    ("kassir_muddat", "Kassaga hisob-kitob paytida muddati o'tgan mahsulotni ko'rib qolsangiz, nima qilasiz?"),
]

SOTUVCHI_QUESTIONS: list[tuple[str, str]] = [
    ("sotuvchi_kutib_olish", "Do'konga kirgan xaridorni qanday kutib olasiz?"),
    ("sotuvchi_ehtiyoj", "Xaridorning nima izlayotganini qanday aniqlaysiz?"),
    ("sotuvchi_topilmasa", "So'ralgan mahsulot bo'lmasa, nima taklif qilasiz?"),
    ("sotuvchi_norozilik", "Xaridor noroziligini qanday hal qilasiz?"),
    ("sotuvchi_qoshimcha", "Qo'shimcha mahsulotni bosim qilmasdan qanday tavsiya qilasiz?"),
    ("sotuvchi_javon", "Javon bo'sh yoki tartibsiz ekanini ko'rsangiz, nima qilasiz?"),
    ("sotuvchi_muddat", "Muddati yaqinlashib qolgan mahsulotni ko'rsangiz, nima qilasiz?"),
    ("sotuvchi_kelishmovchilik", "Hamkasbingiz bilan kelishmovchilik chiqsa, qanday hal qilasiz?"),
]

ROLE_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "kassir": KASSIR_QUESTIONS,
    "sotuvchi": SOTUVCHI_QUESTIONS,
}


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
# olib kelishi mumkin edi).
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
