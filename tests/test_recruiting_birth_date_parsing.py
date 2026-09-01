"""``recruiting_bot._parse_birth_date`` — kun-oy-yil tartibida, turli
formatlarda (raqamli va oy nomi bilan, o'zbek lotin/kirill va ruscha)
yozilgan tug'ilgan sanani tushunish testlari."""

import recruiting_bot


def test_numeric_formats_are_accepted():
    for text in (
        "15.10.2000", "15/10/2000", "15-10-2000", "15,10,2000", "15 10 2000",
        "15.10.2000 yil", "15 10 2000 г",
    ):
        assert recruiting_bot._parse_birth_date(text) == (15, 10, 2000), text


def test_month_name_formats_are_accepted_in_every_language_variant():
    uz_latin_months = [
        "yanvar", "fevral", "mart", "aprel", "may", "iyun",
        "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
    ]
    for month_number, name in enumerate(uz_latin_months, start=1):
        assert recruiting_bot._parse_birth_date(f"15 {name} 2000") == (15, month_number, 2000), name

    # ruscha oy nomi (roditelniy kelishik) + "yil"/"года" qo'shimchasi
    assert recruiting_bot._parse_birth_date("8 fevral 1999 yil") == (8, 2, 1999)
    assert recruiting_bot._parse_birth_date("21 mart 2001") == (21, 3, 2001)
    assert recruiting_bot._parse_birth_date("15 oktyabr 2000") == (15, 10, 2000)
    assert recruiting_bot._parse_birth_date("15 октябрь 2000") == (15, 10, 2000)
    assert recruiting_bot._parse_birth_date("15 октября 2000 года") == (15, 10, 2000)


def test_invalid_date_is_rejected():
    assert recruiting_bot._parse_birth_date("31.02.2020") is None
    assert recruiting_bot._parse_birth_date("31 fevral 2000") is None
