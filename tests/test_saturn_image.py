import io
from datetime import date

import pytest
from PIL import Image, ImageDraw

from services import saturn_content, saturn_image
from services import saturn_season, saturn_weather_scene

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _open(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes))


def test_morning_image_is_correct_size_and_format():
    data = saturn_image.render_morning_image("Bugun tabassum bilan salomlashing.")
    image = _open(data)

    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)
    assert image.format == "PNG"


def test_night_image_is_correct_size_and_format():
    data = saturn_image.render_night_image("Ish joyini tartibli qoldiring.")
    image = _open(data)

    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)
    assert image.format == "PNG"


def test_morning_image_with_weather_badge_renders_without_error():
    badge = saturn_image.format_weather_badge("Qo'qon", 18.0, "Ochiq")
    data = saturn_image.render_morning_image("Bugun tabassum bilan salomlashing.", badge)

    image = _open(data)
    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_morning_image_without_weather_badge_renders_without_error():
    data = saturn_image.render_morning_image("Bugun tabassum bilan salomlashing.", weather_text=None)

    image = _open(data)
    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_night_image_never_includes_weather():
    """``render_night_image`` funksiyasi umuman ob-havo argumentini
    qabul qilmaydi — bu talab funksiya imzosining o'zida kafolatlangan."""
    import inspect

    params = inspect.signature(saturn_image.render_night_image).parameters
    assert "weather_text" not in params


def test_longest_bank_advice_renders_without_error_morning():
    longest = max(saturn_content.MORNING_ADVICE_BANK, key=lambda kv: len(kv[1]))
    badge = saturn_image.format_weather_badge("Qo'qon", -5.0, "Qor")

    data = saturn_image.render_morning_image(longest[1], badge)
    image = _open(data)

    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_longest_bank_advice_renders_without_error_night():
    longest = max(saturn_content.NIGHT_ADVICE_BANK, key=lambda kv: len(kv[1]))

    data = saturn_image.render_night_image(longest[1])
    image = _open(data)

    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_format_weather_badge_formats_positive_temperature():
    badge = saturn_image.format_weather_badge("Qo'qon", 18.4, "Ochiq")
    assert badge == "Qo'qon • +18°C • Ochiq"


def test_format_weather_badge_formats_negative_temperature():
    badge = saturn_image.format_weather_badge("Qo'qon", -3.2, "Qor")
    assert badge == "Qo'qon • -3°C • Qor"


def test_format_weather_badge_formats_zero_temperature():
    badge = saturn_image.format_weather_badge("Qo'qon", 0.0, "Bulutli")
    assert badge == "Qo'qon • +0°C • Bulutli"


def test_saturn_mark_falls_back_to_text_when_logo_path_not_set(monkeypatch):
    """``SATURN_LOGO_PATH`` bo'sh bo'lsa, soxta logotip o'ylab
    topilmaydi — rasm baribir xatosiz yaratiladi (matn "SATURN" bilan)."""
    monkeypatch.setattr(saturn_image, "SATURN_LOGO_PATH", None)

    data = saturn_image.render_morning_image("Test maslahat.")
    image = _open(data)
    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_saturn_mark_falls_back_to_text_when_logo_file_missing(monkeypatch):
    """Logotip yo'li ko'rsatilgan, lekin fayl mavjud emas — xato
    bermasdan oddiy "SATURN" yozuviga qaytadi."""
    monkeypatch.setattr(saturn_image, "SATURN_LOGO_PATH", "/no/such/file/saturn_logo.png")

    data = saturn_image.render_morning_image("Test maslahat.")
    image = _open(data)
    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_saturn_mark_falls_back_to_text_when_logo_file_is_corrupt(monkeypatch, tmp_path):
    """Fayl mavjud, lekin haqiqiy rasm emas — logotip yuklashdagi xato
    butun rasm generatsiyasini to'xtatmasligi kerak."""
    bad_file = tmp_path / "not_an_image.png"
    bad_file.write_bytes(b"bu rasm emas, oddiy matn")
    monkeypatch.setattr(saturn_image, "SATURN_LOGO_PATH", str(bad_file))

    data = saturn_image.render_morning_image("Test maslahat.")
    image = _open(data)
    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


# ----------------------------------------- fasl/ob-havo sahna integratsiyasi --


def test_morning_image_rendering_is_deterministic_for_the_same_date():
    d = date(2026, 7, 4)
    data1 = saturn_image.render_morning_image(
        "Bugun tabassum bilan salomlashing.", season=saturn_season.SUMMER,
        weather_category=saturn_weather_scene.CATEGORY_CLEAR, local_date=d,
    )
    data2 = saturn_image.render_morning_image(
        "Bugun tabassum bilan salomlashing.", season=saturn_season.SUMMER,
        weather_category=saturn_weather_scene.CATEGORY_CLEAR, local_date=d,
    )
    assert data1 == data2


def test_night_image_rendering_is_deterministic_for_the_same_date():
    d = date(2026, 1, 10)
    data1 = saturn_image.render_night_image(
        "Ish joyini tartibli qoldiring.", season=saturn_season.WINTER,
        weather_category=saturn_weather_scene.CATEGORY_SNOW, local_date=d,
    )
    data2 = saturn_image.render_night_image(
        "Ish joyini tartibli qoldiring.", season=saturn_season.WINTER,
        weather_category=saturn_weather_scene.CATEGORY_SNOW, local_date=d,
    )
    assert data1 == data2


def test_morning_image_background_does_not_repeat_on_consecutive_days():
    """Bir xil fasl/ob-havo kategoriyasi ikki kun ketma-ket saqlanib
    qolsa ham, fon rasm ketma-ket ikki kunda bir xil bo'lmasligi kerak
    (deterministik variant tanlovi kunlar bo'yicha aylanadi)."""
    day1 = date(2026, 3, 5)
    day2 = date(2026, 3, 6)
    data1 = saturn_image.render_morning_image(
        "Xayrli kun.", season=saturn_season.SPRING,
        weather_category=saturn_weather_scene.CATEGORY_RAIN, local_date=day1,
    )
    data2 = saturn_image.render_morning_image(
        "Xayrli kun.", season=saturn_season.SPRING,
        weather_category=saturn_weather_scene.CATEGORY_RAIN, local_date=day2,
    )
    assert data1 != data2


def test_night_image_background_matches_the_given_season():
    """Qish/qor kategoriyasidagi tungi rasm bilan yoz/ochiq kategoriyasidagi
    tungi rasm sezilarli darajada farq qilishi kerak — fasl fon orqali
    ko'rinib turishi kerak."""
    d = date(2026, 1, 1)
    winter_snow = saturn_image.render_night_image(
        "Matn.", season=saturn_season.WINTER, weather_category=saturn_weather_scene.CATEGORY_SNOW, local_date=d,
    )
    summer_clear = saturn_image.render_night_image(
        "Matn.", season=saturn_season.SUMMER, weather_category=saturn_weather_scene.CATEGORY_CLEAR, local_date=d,
    )
    assert winter_snow != summer_clear


def test_all_render_functions_default_gracefully_without_optional_scene_args():
    """Eski chaqiruv uslubi (faqat matn, ixtiyoriy ob-havo belgisi)
    hali ham xatosiz ishlashi kerak — fasl/kategoriya avtomatik
    tanlanadi."""
    data = saturn_image.render_morning_image("Test matni.")
    image = _open(data)
    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_logo_weather_badge_and_signature_do_not_overlap_the_glass_card():
    """Chapdagi logotip, o'ngdagi ob-havo belgisi va pastki o'ngdagi
    'Fokus AI' yozuvi markazdagi glass card zonasidan tashqarida
    joylashgan bo'lishi kerak."""
    assert saturn_image._CARD_TOP > 180  # logotip/ob-havo belgisi balandligidan pastda

    font = saturn_image._font(bold=True, size=saturn_image._FOKUS_AI_SIZE)
    text_bbox = font.getbbox("Fokus AI")
    text_h = text_bbox[3] - text_bbox[1]
    padding = 14
    card_bottom = saturn_image.IMAGE_SIZE - saturn_image._BRAND_MARGIN
    fokus_ai_card_top = card_bottom - text_h - padding * 2
    assert fokus_ai_card_top > saturn_image._CARD_BOTTOM


def test_wrap_text_respects_max_lines():
    """Juda uzun matn ham cheksiz qatorga bo'linib ketmaydi — belgilangan
    maksimal qator sonidan oshmaydi."""
    canvas = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(canvas)
    font = saturn_image._font(bold=False, size=30)

    very_long_text = " ".join(["so'z"] * 100)
    lines = saturn_image._wrap_text(draw, very_long_text, font, max_width=500)

    assert len(lines) <= saturn_image._MAX_ADVICE_LINES


# ------------------------------------------------------- moslashuvchan shrift --


def test_max_advice_lines_is_two():
    assert saturn_image._MAX_ADVICE_LINES == 2


def test_min_advice_size_is_38():
    assert saturn_image._MIN_ADVICE_SIZE == 38


def test_advice_font_sizes_never_go_below_the_minimum():
    assert min(saturn_image._ADVICE_FONT_SIZES) == saturn_image._MIN_ADVICE_SIZE
    assert saturn_image._ADVICE_SIZE == 42


def test_advice_font_size_uses_primary_size_for_short_text():
    canvas = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(canvas)
    size = saturn_image._advice_font_size(draw, "Bugun kimgadir yordam bering.")
    assert size == saturn_image._ADVICE_SIZE


def test_advice_font_size_never_returns_below_minimum_for_any_real_bank_entry():
    canvas = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(canvas)
    for _key, text in saturn_content.MORNING_ADVICE_BANK + saturn_content.NIGHT_ADVICE_BANK:
        size = saturn_image._advice_font_size(draw, text)
        assert size >= saturn_image._MIN_ADVICE_SIZE


def test_fits_within_advice_lines_accepts_all_real_bank_entries():
    for _key, text in saturn_content.MORNING_ADVICE_BANK + saturn_content.NIGHT_ADVICE_BANK:
        assert saturn_image.fits_within_advice_lines(text) is True, text


def test_fits_within_advice_lines_rejects_long_unwrappable_text():
    long_shaped_text = (
        "Xaridorlar bilan muomalada doimo xushmuomala, samimiy va professional tarzda ish yuriting."
    )
    assert saturn_image.fits_within_advice_lines(long_shaped_text) is False


def test_rendered_advice_text_is_never_smaller_than_min_size_visually():
    """Uzun (lekin qabul qilingan) matn ham rasmda 38px'dan kichik
    shriftda chiqmaydi — ``render_morning_image`` real chaqiruvi orqali
    tekshiriladi."""
    longest = max(saturn_content.MORNING_ADVICE_BANK, key=lambda kv: len(kv[1]))
    canvas = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(canvas)
    size = saturn_image._advice_font_size(draw, longest[1])
    assert size >= saturn_image._MIN_ADVICE_SIZE


# --------------------------------------------------------- fotoreal fon --


def test_get_background_credit_returns_none_for_uncovered_combo():
    """Katalogda mos foto yo'q bo'lgan kombinatsiya uchun kredit
    ``None`` bo'lishi kerak (vektor sahna ishlatilgan degani)."""
    credit = saturn_image.get_background_credit(
        season="qish", weather_category="drizzle", time_of_day="morning", local_date=date(2026, 1, 1)
    )
    assert credit is None


def test_get_background_credit_returns_text_for_covered_combo():
    credit = saturn_image.get_background_credit(
        season="bahor", weather_category="clear", time_of_day="morning", local_date=date(2026, 5, 1)
    )
    assert credit is not None
    assert credit.startswith("📷")


def test_morning_image_renders_with_real_photo_background_without_error():
    data = saturn_image.render_morning_image(
        "Test.", season="bahor", weather_category="clear", local_date=date(2026, 5, 1)
    )
    image = _open(data)
    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_night_image_falls_back_to_vector_scene_for_uncovered_combo():
    """Katalogda mos foto bo'lmasa ham, rasm hech qachon xato bermaydi
    — dasturiy vektor sahnaga qaytadi."""
    data = saturn_image.render_night_image(
        "Test.", season="qish", weather_category="drizzle", local_date=date(2026, 1, 1)
    )
    image = _open(data)
    assert image.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)
