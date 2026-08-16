import io

import pytest
from PIL import Image

from services import saturn_content, saturn_image

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


def test_wrap_text_respects_max_lines():
    """Juda uzun matn ham cheksiz qatorga bo'linib ketmaydi — belgilangan
    maksimal qator sonidan oshmaydi."""
    from PIL import ImageDraw

    canvas = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(canvas)
    font = saturn_image._font(bold=False, size=30)

    very_long_text = " ".join(["so'z"] * 100)
    lines = saturn_image._wrap_text(draw, very_long_text, font, max_width=500)

    assert len(lines) <= saturn_image._MAX_ADVICE_LINES
