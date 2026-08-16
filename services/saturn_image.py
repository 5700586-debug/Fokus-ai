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

from config import SATURN_LOGO_PATH

logger = logging.getLogger(__name__)

IMAGE_SIZE = 1080
_MARGIN = 90
_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_MORNING_TOP = (255, 226, 155)      # yumshoq oltin
_MORNING_BOTTOM = (255, 145, 110)   # iliq to'q sariq/qizg'ish
_NIGHT_TOP = (13, 27, 58)           # to'q ko'k
_NIGHT_BOTTOM = (30, 45, 82)        # sokin tungi ko'k

_MORNING_TEXT = (58, 32, 20)        # to'q jigarrang — iliq fonda o'qilishi uchun kontrast
_NIGHT_TEXT = (235, 240, 250)       # deyarli oq — to'q fonda kontrast

_TITLE_SIZE = 66
_ADVICE_SIZE = 42
_BADGE_SIZE = 28
_WORDMARK_SIZE = 30
_FOKUS_AI_SIZE = 24

_MAX_ADVICE_LINES = 4


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(_FONTS_DIR / filename), size)


def _vertical_gradient(top_rgb: tuple[int, int, int], bottom_rgb: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), top_rgb)
    draw = ImageDraw.Draw(image)
    for y in range(IMAGE_SIZE):
        ratio = y / (IMAGE_SIZE - 1)
        row_color = tuple(
            int(top_rgb[channel] + (bottom_rgb[channel] - top_rgb[channel]) * ratio) for channel in range(3)
        )
        draw.line([(0, y), (IMAGE_SIZE, y)], fill=row_color)
    return image


def _soft_glow(image: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, int, int]) -> None:
    """Iliq/quyoshli tuyg'u uchun yumshoq, shaffof doira — juda ko'p
    bezaksiz, faqat bitta nozik urg'u."""
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for step in range(radius, 0, -6):
        alpha = int(28 * (1 - step / radius))
        overlay_draw.ellipse(
            [center[0] - step, center[1] - step, center[0] + step, center[1] + step],
            fill=(*color, alpha),
        )
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def _stars(image: Image.Image) -> None:
    """Tungi fon uchun bir nechta kichik, xotirjam yulduzcha — ortiqcha
    bezaksiz, minimal. Faqat sarlavha/maslahat matni joylashadigan
    o'rta zonadan (taxminan Y 380-900) TASHQARIDA joylashtirilgan —
    aks holda uzun (4 qatorli) maslahat matni bilan yulduzcha
    ustma-ust tushib, o'qilishni buzishi mumkin edi.
    """
    draw = ImageDraw.Draw(image)
    positions = [
        # Yuqori zona (matn boshlanishidan oldin)
        (120, 140), (940, 110), (860, 260), (180, 320), (1000, 220), (250, 90), (60, 250),
        # Pastki zona (matn tugagandan keyin, "Fokus AI" yozuvidan yuqorida)
        (960, 930), (140, 960), (1020, 970), (90, 920), (980, 890),
    ]
    for x, y in positions:
        radius = 2 if (x + y) % 3 else 3
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(255, 255, 255))


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


def render_morning_image(advice_text: str, weather_text: str | None = None) -> bytes:
    image = _vertical_gradient(_MORNING_TOP, _MORNING_BOTTOM)
    _soft_glow(image, center=(IMAGE_SIZE // 2, 260), radius=380, color=(255, 250, 210))

    draw = ImageDraw.Draw(image)

    if weather_text:
        _draw_weather_badge(draw, weather_text, _MORNING_TEXT)

    _draw_saturn_mark(draw, image, _MORNING_TEXT)

    title_font = _font(bold=True, size=_TITLE_SIZE)
    title_lines = _wrap_text(draw, "Xayrli tong, Saturn jamoasi!", title_font, IMAGE_SIZE - 2 * _MARGIN)
    next_y = _draw_multiline_centered(draw, title_lines, title_font, top_y=400, fill=_MORNING_TEXT, line_spacing=10)

    advice_font = _font(bold=False, size=_ADVICE_SIZE)
    advice_lines = _wrap_text(draw, advice_text, advice_font, IMAGE_SIZE - 2 * _MARGIN - 40)
    _draw_multiline_centered(draw, advice_lines, advice_font, top_y=next_y + 40, fill=_MORNING_TEXT)

    _draw_fokus_ai_wordmark(draw, _MORNING_TEXT)

    return _encode_png(image)


def render_night_image(advice_text: str) -> bytes:
    image = _vertical_gradient(_NIGHT_TOP, _NIGHT_BOTTOM)
    _stars(image)

    draw = ImageDraw.Draw(image)
    _draw_saturn_mark(draw, image, _NIGHT_TEXT)

    title_font = _font(bold=True, size=_TITLE_SIZE)
    title_lines = _wrap_text(draw, "Xayrli tun, Saturn jamoasi!", title_font, IMAGE_SIZE - 2 * _MARGIN)
    next_y = _draw_multiline_centered(draw, title_lines, title_font, top_y=420, fill=_NIGHT_TEXT, line_spacing=10)

    advice_font = _font(bold=False, size=_ADVICE_SIZE)
    advice_lines = _wrap_text(draw, advice_text, advice_font, IMAGE_SIZE - 2 * _MARGIN - 40)
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
