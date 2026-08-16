"""Saturn tonggi/tungi rasmli xabari uchun 1080x1080 PNG generatsiyasi.

Butunlay Pillow orqali, dasturiy chizish bilan — matn AI-generatsiya
qilingan rasmning ICHIGA yozdirilmaydi (AI imlo/logotipni buzishi
mumkin, qarang vazifa talabi). Hamma narsa: fon gradienti, sarlavha,
maslahat matni, ob-havo belgisi, Saturn logotipi/yozuvi va "Fokus AI"
yozuvi — aniq koordinata bilan, dastur orqali joylashtiriladi.

Natija doim xotirada (``io.BytesIO``) tayyorlanadi — vaqtinchalik faylga
yozish/tozalash shart emas, aiogram ``BufferedInputFile`` orqali
to'g'ridan-to'g'ri baytlardan yuboradi.
"""

import io
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import company_time
from config import SATURN_LOGO_PATH
from services import saturn_scene
from services import saturn_season
from services import saturn_weather_scene

logger = logging.getLogger(__name__)

IMAGE_SIZE = saturn_scene.IMAGE_SIZE
_MARGIN = 90
_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_MORNING_TEXT = (58, 32, 20)        # to'q jigarrang — glass card ustida o'qilishi uchun kontrast
_NIGHT_TEXT = (235, 240, 250)       # deyarli oq — to'q glass card ustida kontrast

_CARD_TOP = 370
_CARD_BOTTOM = 730

_TITLE_SIZE = 66
_ADVICE_SIZE = 30  # 100 belgigacha bo'lgan matn ham 2 qatorga kesilmasdan sig'ishi uchun
_BADGE_SIZE = 28
_WORDMARK_SIZE = 30
_FOKUS_AI_SIZE = 24

_MAX_ADVICE_LINES = 2


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(_FONTS_DIR / filename), size)


def _draw_glass_card(image: Image.Image, top: int, bottom: int, light: bool) -> None:
    """Sarlavha/maslahat matni ortidagi yarim shaffof "glass card" —
    fon qanchalik "band"/to'q bo'lishidan qat'i nazar matn o'qilishini
    kafolatlaydi (qarang talab: matn fonga cho'kib ketmasligi kerak)."""
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    fill = (255, 255, 255, 165) if light else (8, 12, 26, 155)
    overlay_draw.rounded_rectangle(
        [_MARGIN - 20, top, IMAGE_SIZE - _MARGIN + 20, bottom], radius=36, fill=fill
    )
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines[:_MAX_ADVICE_LINES]


def _draw_multiline_centered(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    top_y: int,
    fill: tuple[int, int, int],
    line_spacing: int = 14,
) -> int:
    """Har bir qatorni gorizontal markazlab chizadi, keyingi bo'sh
    Y koordinatasini qaytaradi."""
    y = top_y
    for line in lines:
        width = draw.textlength(line, font=font)
        x = (IMAGE_SIZE - width) / 2
        draw.text((x, y), line, font=font, fill=fill)
        bbox = font.getbbox(line)
        line_height = bbox[3] - bbox[1]
        y += line_height + line_spacing
    return int(y)


def _draw_saturn_mark(draw: ImageDraw.ImageDraw, image: Image.Image, text_color: tuple[int, int, int]) -> None:
    """Asl logotip fayli (``SATURN_LOGO_PATH``) mavjud va ochilsa —
    o'sha ishlatiladi. Aks holda (fayl yo'q/hali qo'shilmagan) — soxta
    logotip o'ylab topilmaydi, oddiy "SATURN" yozuvi chiziladi.
    """
    corner_x, corner_y = _MARGIN, _MARGIN

    if SATURN_LOGO_PATH:
        try:
            logo_path = Path(SATURN_LOGO_PATH)
            if logo_path.is_file():
                logo = Image.open(logo_path).convert("RGBA")
                target_height = 90
                ratio = target_height / logo.height
                logo = logo.resize((max(1, int(logo.width * ratio)), target_height))
                image.paste(logo, (corner_x, corner_y), logo)
                return
        except Exception as error:  # noqa: BLE001 - logotip yuklanmasa ham rasm yaratilishi to'xtamasin
            logger.warning("Saturn logotipini yuklab bo'lmadi (%s): %r", SATURN_LOGO_PATH, error)

    font = _font(bold=True, size=_WORDMARK_SIZE)
    draw.text((corner_x, corner_y), "SATURN", font=font, fill=text_color)


def _draw_fokus_ai_wordmark(draw: ImageDraw.ImageDraw, text_color: tuple[int, int, int]) -> None:
    font = _font(bold=False, size=_FOKUS_AI_SIZE)
    text = "Fokus AI"
    width = draw.textlength(text, font=font)
    x = IMAGE_SIZE - _MARGIN - width
    y = IMAGE_SIZE - _MARGIN - _FOKUS_AI_SIZE
    draw.text((x, y), text, font=font, fill=text_color)


def _draw_weather_badge(draw: ImageDraw.ImageDraw, badge_text: str, text_color: tuple[int, int, int]) -> None:
    """Yuqori o'ng burchakda kichik, chiroyli belgi — katta joy
    egallamaydi, asosiy xabarga xalaqit bermaydi."""
    font = _font(bold=False, size=_BADGE_SIZE)
    width = draw.textlength(badge_text, font=font)
    padding_x, padding_y = 20, 12
    box_right = IMAGE_SIZE - _MARGIN
    box_left = box_right - width - padding_x * 2
    box_top = _MARGIN
    box_bottom = box_top + _BADGE_SIZE + padding_y * 2

    draw.rounded_rectangle(
        [box_left, box_top, box_right, box_bottom], radius=18, fill=(255, 255, 255, 235)
    )
    draw.text((box_left + padding_x, box_top + padding_y - 2), badge_text, font=font, fill=(70, 45, 20))


def render_morning_image(
    advice_text: str,
    weather_text: str | None = None,
    *,
    season: str | None = None,
    weather_category: str | None = None,
    local_date=None,
    variant: int | None = None,
) -> bytes:
    """Fasl/ob-havoga mos original fon (``services/saturn_scene.py``)
    ustiga matn "glass card" orqali joylashtiriladi. ``season``/
    ``weather_category``/``local_date``/``variant`` — ixtiyoriy
    (berilmasa, joriy sana va fasl-standart sahna ishlatiladi; qarang
    ``services/saturn_group.py`` ishlab chiqarish chaqiruvi)."""
    local_date = local_date or company_time.today()
    season = season or saturn_season.season_for_date(local_date)
    weather_category = weather_category or saturn_weather_scene.CATEGORY_SEASON_DEFAULT
    if variant is None:
        variant = saturn_scene.variant_index(local_date, offset=0)

    image = saturn_scene.render_background(season, weather_category, saturn_scene.TIME_MORNING, variant)

    draw = ImageDraw.Draw(image)

    if weather_text:
        _draw_weather_badge(draw, weather_text, _MORNING_TEXT)

    _draw_saturn_mark(draw, image, _MORNING_TEXT)

    _draw_glass_card(image, _CARD_TOP, _CARD_BOTTOM, light=True)
    draw = ImageDraw.Draw(image)

    title_font = _font(bold=True, size=_TITLE_SIZE)
    title_lines = _wrap_text(draw, "Xayrli tong, Saturn jamoasi!", title_font, IMAGE_SIZE - 2 * _MARGIN)
    next_y = _draw_multiline_centered(draw, title_lines, title_font, top_y=400, fill=_MORNING_TEXT, line_spacing=10)

    advice_font = _font(bold=False, size=_ADVICE_SIZE)
    advice_lines = _wrap_text(draw, advice_text, advice_font, IMAGE_SIZE - 2 * _MARGIN - 10)
    _draw_multiline_centered(draw, advice_lines, advice_font, top_y=next_y + 40, fill=_MORNING_TEXT)

    _draw_fokus_ai_wordmark(draw, _MORNING_TEXT)

    return _encode_png(image)


def render_night_image(
    advice_text: str,
    *,
    season: str | None = None,
    weather_category: str | None = None,
    local_date=None,
    variant: int | None = None,
) -> bytes:
    """``render_morning_image`` bilan bir xil sahna tizimi, lekin
    ob-havo argumenti UMUMAN QABUL QILINMAYDI — bu tungi rasmda
    hech qachon ob-havo matni ko'rsatilmasligi funksiya imzosining
    o'zida kafolatlangan (qarang tegishli test)."""
    local_date = local_date or company_time.today()
    season = season or saturn_season.season_for_date(local_date)
    weather_category = weather_category or saturn_weather_scene.CATEGORY_SEASON_DEFAULT
    if variant is None:
        variant = saturn_scene.variant_index(local_date, offset=1)

    image = saturn_scene.render_background(season, weather_category, saturn_scene.TIME_NIGHT, variant)

    draw = ImageDraw.Draw(image)
    _draw_saturn_mark(draw, image, _NIGHT_TEXT)

    _draw_glass_card(image, _CARD_TOP, _CARD_BOTTOM, light=False)
    draw = ImageDraw.Draw(image)

    title_font = _font(bold=True, size=_TITLE_SIZE)
    title_lines = _wrap_text(draw, "Xayrli tun, Saturn jamoasi!", title_font, IMAGE_SIZE - 2 * _MARGIN)
    next_y = _draw_multiline_centered(draw, title_lines, title_font, top_y=420, fill=_NIGHT_TEXT, line_spacing=10)

    advice_font = _font(bold=False, size=_ADVICE_SIZE)
    advice_lines = _wrap_text(draw, advice_text, advice_font, IMAGE_SIZE - 2 * _MARGIN - 10)
    _draw_multiline_centered(draw, advice_lines, advice_font, top_y=next_y + 40, fill=_NIGHT_TEXT)

    _draw_fokus_ai_wordmark(draw, _NIGHT_TEXT)

    return _encode_png(image)


def format_weather_badge(city: str, temperature_c: float, description: str) -> str:
    sign = "+" if temperature_c >= 0 else ""
    return f"{city} • {sign}{temperature_c:.0f}°C • {description}"


def _encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
